import os
from dataclasses import dataclass, replace
from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Tuple


DEFAULT_ALLOWED_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/jpg",
        "image/webp",
    }
)


@dataclass(frozen=True)
class Settings:
    """Centralised application configuration."""

    max_content_length: int
    allowed_mime_types: FrozenSet[str]
    max_images_per_request: int
    min_images_per_request: int
    http_pool_connections: int
    http_pool_maxsize: int
    http_max_retries: int
    http_backoff_factor: float
    dashscope_api_key: Optional[str]
    dashscope_model: str
    dashscope_endpoint: str
    dashscope_timeout: Tuple[int, int]
    dashscope_force_mock: bool
    log_dir: str
    log_file: str
    log_level: str
    analysis_prompt: str

    @classmethod
    def from_env(cls, overrides: Optional[Mapping[str, object]] = None) -> "Settings":
        overrides = dict(overrides or {})
        allowed_mime_env = os.getenv("ALLOWED_MIME_TYPES")
        if allowed_mime_env:
            allowed_mime_types = frozenset(
                {
                    item.strip().lower()
                    for item in allowed_mime_env.split(",")
                    if item.strip()
                }
            )
        else:
            allowed_mime_types = DEFAULT_ALLOWED_MIME_TYPES

        dashscope_timeout = (
            int(os.getenv("DASHSCOPE_CONNECT_TIMEOUT", "10")),
            int(os.getenv("DASHSCOPE_READ_TIMEOUT", "120")),
        )

        analysis_prompt = os.getenv(
            "DASHSCOPE_ANALYSIS_PROMPT",
            (
                "You are an expert vision model assisting with early forest fire "
                "detection. Analyse the provided image, focus on identifying "
                "visible smoke columns, embers, flame fronts, or reflections. "
                "Estimate the likelihood of an active fire within the next five "
                "minutes and describe any visible risks. Return concise natural "
                "language observations including risk level and contributing "
                "factors."
            ),
        )

        data: Dict[str, object] = {
            "max_content_length": int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024))),
            "allowed_mime_types": allowed_mime_types,
            "max_images_per_request": int(os.getenv("MAX_IMAGES_PER_REQUEST", "2")),
            "min_images_per_request": int(os.getenv("MIN_IMAGES_PER_REQUEST", "1")),
            "http_pool_connections": int(os.getenv("HTTP_POOL_CONNECTIONS", "10")),
            "http_pool_maxsize": int(os.getenv("HTTP_POOL_MAXSIZE", "20")),
            "http_max_retries": int(os.getenv("HTTP_MAX_RETRIES", "3")),
            "http_backoff_factor": float(os.getenv("HTTP_BACKOFF_FACTOR", "1.0")),
            "dashscope_api_key": os.getenv("DASHSCOPE_API_KEY"),
            "dashscope_model": os.getenv("DASHSCOPE_MODEL", "qwen-vl-max"),
            "dashscope_endpoint": os.getenv(
                "DASHSCOPE_ENDPOINT",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ),
            "dashscope_timeout": dashscope_timeout,
            "dashscope_force_mock": os.getenv("DASHSCOPE_FORCE_MOCK", "false").lower()
            in {"1", "true", "yes"},
            "log_dir": os.getenv("LOG_DIR", "logs"),
            "log_file": os.getenv("LOG_FILE", "app.log"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "analysis_prompt": analysis_prompt,
        }
        data.update(overrides)

        # Ensure values are the correct types after overrides
        allowed_mime = data.get("allowed_mime_types", allowed_mime_types)
        if isinstance(allowed_mime, Iterable) and not isinstance(allowed_mime, str):
            data["allowed_mime_types"] = frozenset(map(str.lower, allowed_mime))
        else:
            data["allowed_mime_types"] = allowed_mime_types

        return cls(**data)  # type: ignore[arg-type]

    def merge(self, overrides: Mapping[str, object]) -> "Settings":
        if not overrides:
            return self
        return replace(self, **overrides)
