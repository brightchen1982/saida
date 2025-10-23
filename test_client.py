"""Simple client script to exercise the fire detection API locally."""

from __future__ import annotations

import argparse
import json
import mimetypes
import pathlib
import sys
import time
from typing import List

import requests

DEFAULT_ENDPOINT = "http://127.0.0.1:6000/ai_enhanced_fire_detect"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test client for the AI enhanced fire detection API")
    parser.add_argument("images", nargs="+", help="Path to 1-2 image files to upload")
    parser.add_argument(
        "--url",
        default=DEFAULT_ENDPOINT,
        help=f"Target endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Request timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response",
    )
    return parser


def validate_paths(paths: List[str]) -> List[pathlib.Path]:
    resolved = []
    for raw in paths:
        path = pathlib.Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")
        resolved.append(path)
    if not resolved:
        raise ValueError("At least one image path must be supplied")
    if len(resolved) > 2:
        raise ValueError("The API supports a maximum of two images per request")
    return resolved


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        image_paths = validate_paths(args.images)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
        return

    files = []
    for path in image_paths:
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"
        files.append(("images", (path.name, path.open("rb"), mime_type)))

    start_time = time.perf_counter()
    try:
        response = requests.post(args.url, files=files, timeout=args.timeout)
    except requests.RequestException as exc:
        parser.error(f"HTTP request failed: {exc}")
        return
    finally:
        for _, (name, handle, _) in files:
            handle.close()

    duration = time.perf_counter() - start_time
    print(f"Response status: {response.status_code} ({duration:.2f}s)")

    if args.pretty:
        try:
            payload = response.json()
        except ValueError:
            print(response.text)
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(response.text)


if __name__ == "__main__":
    sys.exit(main())
