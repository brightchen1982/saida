"""Example configuration overrides for the Forest Fire Flask API.

Rename this file to `config.py` and adjust the values as needed. The `CONFIG`
Dictionary will be passed into the application factory at start-up when running
`python app.py`. Environment variables take precedence over these overrides.
"""

CONFIG = {
    # Maximum allowed payload size (bytes) for uploaded images.
    "max_content_length": 10 * 1024 * 1024,
    # Optional override for the accepted MIME types.
    "allowed_mime_types": {
        "image/jpeg",
        "image/png",
        "image/jpg",
        "image/webp",
    },
    # DashScope (阿里云通义) API configuration.
    "dashscope_api_key": "your_api_key_here",
    "dashscope_model": "qwen-vl-max",
    "dashscope_endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    # Connection pooling behaviour for outbound HTTP calls.
    "http_pool_connections": 10,
    "http_pool_maxsize": 20,
    "http_max_retries": 3,
    "http_backoff_factor": 1.0,
    # Logging configuration.
    "log_dir": "logs",
    "log_file": "app.log",
    "log_level": "INFO",
}
