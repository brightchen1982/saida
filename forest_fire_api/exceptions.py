from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ForestFireAPIError(Exception):
    """Base class for structured API errors."""

    message: str
    status_code: int = 500
    error_code: str = "internal_error"
    details: Optional[Dict[str, Any]] = None

    def to_response(self) -> Dict[str, Any]:
        payload = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class ValidationError(ForestFireAPIError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=400, error_code="invalid_request", details=details)


class ImageProcessingError(ForestFireAPIError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=422, error_code="image_processing_error", details=details)


class ExternalServiceError(ForestFireAPIError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code="external_service_error",
            details=details,
        )


class ConfigurationError(ForestFireAPIError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=500, error_code="configuration_error")
