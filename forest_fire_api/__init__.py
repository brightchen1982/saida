from __future__ import annotations

import atexit
from typing import Mapping, Optional

from flask import Flask, jsonify, current_app
from flask_cors import CORS

from .config import Settings
from .dashscope_client import DashScopeClient
from .exceptions import ForestFireAPIError
from .http_client import build_http_session
from .logging_utils import setup_logging


def create_app(config_override: Optional[Mapping[str, object]] = None) -> Flask:
    """Application factory configuring logging, HTTP pooling, and DashScope integration."""
    settings = Settings.from_env(config_override)
    app = Flask(__name__)

    app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length
    app.config["ALLOWED_MIME_TYPES"] = settings.allowed_mime_types
    app.config["MAX_IMAGES_PER_REQUEST"] = settings.max_images_per_request
    app.config["MIN_IMAGES_PER_REQUEST"] = settings.min_images_per_request
    app.config["DASHSCOPE_MODEL"] = settings.dashscope_model
    app.config["APP_SETTINGS"] = settings

    CORS(app, resources={r"/ai_enhanced_fire_detect": {"origins": "*"}})

    listener = setup_logging(settings)
    app.extensions["log_listener"] = listener

    session = build_http_session(settings)
    app.extensions["http_session"] = session
    dashscope_client = DashScopeClient(session=session, settings=settings)
    app.extensions["dashscope_client"] = dashscope_client

    def _close_session() -> None:
        try:
            session.close()
        except Exception:
            pass

    atexit.register(_close_session)

    from .routes import bp as api_bp

    app.register_blueprint(api_bp)

    @app.errorhandler(ForestFireAPIError)
    def handle_known_errors(error: ForestFireAPIError):
        current_app.logger.warning(
            "API error occurred (%s): %s", error.error_code, error.message
        )
        payload = error.to_response()
        payload["status"] = "error"
        return jsonify(payload), error.status_code

    @app.errorhandler(Exception)
    def handle_unknown_error(error: Exception):
        current_app.logger.exception("Unhandled exception: %s", error)
        return (
            jsonify(
                {
                    "status": "error",
                    "error": {
                        "code": "internal_server_error",
                        "message": "An unexpected server error occurred.",
                    },
                }
            ),
            500,
        )

    @app.get("/health")
    def healthcheck():
        return jsonify({"status": "ok"}), 200

    return app


app = create_app()
