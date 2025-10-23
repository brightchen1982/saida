from __future__ import annotations

import argparse
import importlib
import logging
from typing import Any, Dict, Mapping

from forest_fire_api import create_app

logger = logging.getLogger(__name__)


def load_runtime_config() -> Dict[str, Any]:
    try:
        module = importlib.import_module("config")
    except ModuleNotFoundError:
        return {}

    overrides = getattr(module, "CONFIG", None)
    if isinstance(overrides, Mapping):
        return dict(overrides)

    logger.warning(
        "Runtime config module found but no CONFIG mapping was provided. Ignoring overrides."
    )
    return {}


app = create_app(load_runtime_config() or None)


def parse_cli_arguments() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Forest fire enhanced detection service")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind the Flask server")
    parser.add_argument("--port", default=6000, type=int, help="Port to bind the Flask server")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run the server in debug mode (not recommended for production)",
    )
    return vars(parser.parse_args())


if __name__ == "__main__":
    args = parse_cli_arguments()
    logger.info(
        "Starting Flask development server on %s:%s debug=%s", args["host"], args["port"], args["debug"]
    )
    app.run(host=args["host"], port=args["port"], debug=args["debug"])  # pragma: no cover
