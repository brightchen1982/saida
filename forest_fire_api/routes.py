from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import List

from flask import Blueprint, current_app, jsonify, request

from .dashscope_client import DashScopeClient
from .exceptions import (
    ExternalServiceError,
    ForestFireAPIError,
    ValidationError,
)
from .image_processing import (
    PreparedImage,
    annotate_image,
    managed_temp_dir,
    prepare_image,
    save_annotated_image,
)

bp = Blueprint("forest_fire", __name__)


@bp.route("/ai_enhanced_fire_detect", methods=["POST"])
def ai_enhanced_fire_detect():
    """Handle enhanced fire detection requests with validation, filtering, and DashScope analysis."""
    start_time = time.perf_counter()
    request_id = uuid.uuid4().hex
    logger = current_app.logger
    logger.info("Request %s received from %s", request_id, request.remote_addr)

    files = request.files.getlist("images") or request.files.getlist("image")
    if not files:
        raise ValidationError("At least one image file must be uploaded under the 'images' field.")

    max_images = current_app.config.get("MAX_IMAGES_PER_REQUEST", 2)
    min_images = current_app.config.get("MIN_IMAGES_PER_REQUEST", 1)

    if len(files) < min_images:
        raise ValidationError(f"At least {min_images} image(s) must be provided.")
    if len(files) > max_images:
        raise ValidationError(f"At most {max_images} image(s) can be processed per request.")

    allowed_types = current_app.config["ALLOWED_MIME_TYPES"]
    max_length = current_app.config["MAX_CONTENT_LENGTH"]

    dashscope_client: DashScopeClient = current_app.extensions["dashscope_client"]

    results: List[dict] = []
    annotated_images: List[dict] = []

    with managed_temp_dir() as workspace:
        for index, file_storage in enumerate(files, start=1):
            logger.info(
                "Request %s: processing image %s/%s -> %s",
                request_id,
                index,
                len(files),
                file_storage.filename,
            )

            file_storage.stream.seek(0)
            prepared: PreparedImage = prepare_image(file_storage, allowed_types, max_length)

            logger.info(
                "Request %s: prepared image %s size=%dx%d thermal=%s local_fire_probability=%.3f",
                request_id,
                prepared.filename,
                prepared.width,
                prepared.height,
                prepared.is_thermal,
                prepared.fire_probability,
            )

            if prepared.is_thermal:
                summary = "Thermal image detected and skipped from DashScope analysis."
                annotated = annotate_image(prepared.image, summary, fire_detected=False)
                encoded = save_annotated_image(
                    annotated,
                    workspace,
                    Path(prepared.filename).stem,
                    prepared.image_format,
                )
                results.append(
                    {
                        "filename": prepared.filename,
                        "width": prepared.width,
                        "height": prepared.height,
                        "fire_detected": False,
                        "confidence": None,
                        "analysis_summary": summary,
                        "local_fire_probability": prepared.fire_probability,
                        "is_thermal": True,
                        "source": "thermal-filter",
                    }
                )
                annotated_images.append(
                    {
                        "filename": prepared.filename,
                        "image_base64": encoded,
                    }
                )
                continue

            image_start = time.perf_counter()
            try:
                analysis = dashscope_client.analyze_image(
                    prepared.raw_bytes,
                    prepared.image_format,
                    request_id=request_id,
                    context={
                        "filename": prepared.filename,
                        "local_probability": prepared.fire_probability,
                    },
                )
            except ForestFireAPIError:
                raise
            except Exception as exc:
                logger.exception(
                    "Request %s: unexpected error during DashScope analysis for %s",
                    request_id,
                    prepared.filename,
                )
                raise ExternalServiceError(
                    "Unexpected error while invoking DashScope service.",
                    details={"filename": prepared.filename, "error": str(exc)},
                ) from exc

            duration_ms = (time.perf_counter() - image_start) * 1000
            summary = analysis.summary
            annotated = annotate_image(prepared.image, summary, analysis.fire_detected)
            encoded = save_annotated_image(
                annotated,
                workspace,
                Path(prepared.filename).stem,
                prepared.image_format,
            )

            results.append(
                {
                    "filename": prepared.filename,
                    "width": prepared.width,
                    "height": prepared.height,
                    "fire_detected": analysis.fire_detected,
                    "confidence": analysis.confidence,
                    "analysis_summary": summary,
                    "local_fire_probability": prepared.fire_probability,
                    "is_thermal": False,
                    "source": "dashscope",
                    "dashscope_model": current_app.config.get("DASHSCOPE_MODEL"),
                    "latency_ms": round(duration_ms, 2),
                    "raw_response": analysis.raw_response,
                }
            )
            annotated_images.append(
                {
                    "filename": prepared.filename,
                    "image_base64": encoded,
                }
            )

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Request %s completed successfully in %.2f ms", request_id, duration_ms
    )

    return (
        jsonify(
            {
                "status": "success",
                "request_id": request_id,
                "results": results,
                "annotated_images": annotated_images,
                "duration_ms": round(duration_ms, 2),
            }
        ),
        200,
    )
