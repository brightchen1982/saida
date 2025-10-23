from __future__ import annotations

import atexit
import base64
import io
import logging
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

import cv2  # type: ignore
import numpy as np
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .exceptions import ImageProcessingError, ValidationError

logger = logging.getLogger(__name__)

_TEMP_DIRECTORIES: set[Path] = set()
_TEMP_LOCK = threading.Lock()


@dataclass
class PreparedImage:
    filename: str
    content_type: str
    image_format: str
    width: int
    height: int
    image: Image.Image
    raw_bytes: bytes
    is_thermal: bool
    fire_probability: float


@contextmanager
def managed_temp_dir(prefix: str = "fire-detect-"):
    """Yield a temporary directory and guarantee cleanup via context management and atexit."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    with _TEMP_LOCK:
        _TEMP_DIRECTORIES.add(path)
    try:
        yield path
    finally:
        try:
            shutil.rmtree(path, ignore_errors=True)
        finally:
            with _TEMP_LOCK:
                _TEMP_DIRECTORIES.discard(path)


def _cleanup_temp_directories() -> None:
    with _TEMP_LOCK:
        directories = list(_TEMP_DIRECTORIES)
        _TEMP_DIRECTORIES.clear()
    for directory in directories:
        try:
            shutil.rmtree(directory, ignore_errors=True)
        except Exception as exc:
            logger.debug("Failed to cleanup temp directory %s: %s", directory, exc)


atexit.register(_cleanup_temp_directories)


def prepare_image(
    file_storage: FileStorage,
    allowed_mime_types: FrozenSet[str],
    max_content_length: int,
) -> PreparedImage:
    """Validate upload metadata and decode the image while minimising extra copies."""
    filename = secure_filename(file_storage.filename or "image.jpg")
    if not filename:
        raise ValidationError("Uploaded file must include a valid filename.")

    content_type = (file_storage.mimetype or "").lower()
    if content_type and content_type not in allowed_mime_types:
        raise ValidationError(
            f"Unsupported file type '{content_type}'. Allowed types: {', '.join(sorted(allowed_mime_types))}."
        )

    try:
        raw_bytes = file_storage.read()
    except Exception as exc:
        raise ImageProcessingError(
            f"Failed to read uploaded image '{filename}'."
        ) from exc

    if not raw_bytes:
        raise ValidationError(f"Uploaded image '{filename}' is empty.")

    if len(raw_bytes) > max_content_length:
        raise ValidationError(
            f"Uploaded image '{filename}' exceeds the maximum allowed size of {max_content_length} bytes."
        )

    try:
        with Image.open(io.BytesIO(raw_bytes)) as image:
            image.load()
            rgb_image = image.convert("RGB")
            image_format = (image.format or content_type.split("/")[-1] or "jpeg").lower()
            array = np.asarray(rgb_image)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProcessingError(
            f"Unable to decode image '{filename}'. Please provide a valid image file."
        ) from exc

    width, height = rgb_image.size
    is_thermal = detect_thermal(array)
    fire_probability = estimate_fire_probability(array)
    del array

    logger.debug(
        "Prepared image '%s' (%dx%d) thermal=%s estimated_fire_probability=%.4f",
        filename,
        width,
        height,
        is_thermal,
        fire_probability,
    )

    return PreparedImage(
        filename=filename,
        content_type=content_type or f"image/{image_format}",
        image_format=image_format,
        width=width,
        height=height,
        image=rgb_image,
        raw_bytes=raw_bytes,
        is_thermal=is_thermal,
        fire_probability=fire_probability,
    )


def detect_thermal(array: np.ndarray) -> bool:
    """Heuristically flag thermal imagery using down-sampled HSV variance and colour diversity."""
    if array.ndim != 3 or array.shape[2] != 3:
        return True

    if array.shape[0] > 512 or array.shape[1] > 512:
        sampling_factor = max(array.shape[0] // 512, array.shape[1] // 512, 1)
        array = array[::sampling_factor, ::sampling_factor, :]

    hsv = cv2.cvtColor(array, cv2.COLOR_RGB2HSV)
    saturation_mean = float(np.mean(hsv[:, :, 1]))
    value_std = float(np.std(hsv[:, :, 2]))

    flattened = array.reshape(-1, 3)
    unique_colors = len(np.unique(flattened, axis=0))
    unique_ratio = unique_colors / float(flattened.shape[0])

    thermal = saturation_mean < 25.0 or value_std < 18.0 or unique_ratio < 0.08

    logger.debug(
        "Thermal detection metrics: saturation_mean=%.2f value_std=%.2f unique_ratio=%.4f -> %s",
        saturation_mean,
        value_std,
        unique_ratio,
        thermal,
    )

    return thermal


def estimate_fire_probability(array: np.ndarray) -> float:
    """Estimate fire likelihood via HSV masking of warm spectra and global brightness."""
    if array.ndim != 3 or array.shape[2] != 3:
        return 0.0

    if array.shape[0] > 640 or array.shape[1] > 640:
        sampling_factor = max(array.shape[0] // 640, array.shape[1] // 640, 1)
        array = array[::sampling_factor, ::sampling_factor, :]

    hsv = cv2.cvtColor(array, cv2.COLOR_RGB2HSV)

    lower_red1 = np.array([0, 70, 80])
    upper_red1 = np.array([15, 255, 255])
    lower_red2 = np.array([160, 70, 80])
    upper_red2 = np.array([179, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    combined_mask = cv2.bitwise_or(mask1, mask2)

    red_ratio = float(cv2.countNonZero(combined_mask)) / float(combined_mask.size or 1)

    brightness = float(np.mean(hsv[:, :, 2])) / 255.0
    probability = max(0.0, min(1.0, 0.65 * red_ratio + 0.35 * brightness))

    logger.debug(
        "Estimated fire probability: red_ratio=%.4f brightness=%.4f -> %.4f",
        red_ratio,
        brightness,
        probability,
    )

    return probability


def annotate_image(image: Image.Image, summary: str, fire_detected: bool) -> Image.Image:
    """Overlay a status banner with the model summary while keeping the source image intact."""
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    font = ImageFont.load_default()

    safe_summary = summary.strip() or "Analysis completed."
    if len(safe_summary) > 220:
        safe_summary = safe_summary[:217] + "..."

    padding = 12
    text_bbox = draw.multiline_textbbox((0, 0), safe_summary, font=font, spacing=4)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    rectangle_height = text_height + padding * 2
    rectangle_color = (214, 45, 32) if fire_detected else (45, 106, 204)

    draw.rectangle(
        [0, 0, max(annotated.width, text_width + padding * 2), rectangle_height],
        fill=rectangle_color,
    )
    draw.multiline_text(
        (padding, padding),
        safe_summary,
        fill=(255, 255, 255),
        font=font,
        spacing=4,
    )

    return annotated


def _normalise_image_format(format_hint: str) -> str:
    format_upper = (format_hint or "jpeg").upper()
    if format_upper in {"JPG", "JPEG"}:
        return "JPEG"
    return format_upper


def image_to_base64(image: Image.Image, format_hint: str) -> str:
    """Encode a PIL image to Base64 while respecting the preferred output format."""
    output = io.BytesIO()
    format_upper = _normalise_image_format(format_hint)
    try:
        image.save(output, format=format_upper, quality=90)
    except ValueError:
        image.save(output, format="JPEG", quality=90)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return encoded


def save_annotated_image(
    image: Image.Image,
    workspace: Path,
    base_filename: str,
    format_hint: str,
) -> str:
    """Persist an annotated image to disk when possible, with in-memory fallback."""
    format_upper = _normalise_image_format(format_hint)
    extension = "jpg" if format_upper == "JPEG" else format_upper.lower()
    temp_path = workspace / f"{base_filename}_annotated.{extension}"

    try:
        image.save(temp_path, format=format_upper)
        encoded = base64.b64encode(temp_path.read_bytes()).decode("ascii")
    except Exception as exc:
        logger.warning(
            "Failed to persist annotated image for %s (%s). Falling back to in-memory encoding: %s",
            base_filename,
            temp_path,
            exc,
        )
        encoded = image_to_base64(image, format_hint)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception as cleanup_exc:
            logger.debug("Unable to remove temporary image %s: %s", temp_path, cleanup_exc)

    return encoded
