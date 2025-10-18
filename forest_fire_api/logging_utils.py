import atexit
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from queue import Queue
from typing import Optional

from .config import Settings


_log_queue: "Queue[logging.LogRecord]" = Queue(-1)
_listener: Optional[logging.handlers.QueueListener] = None


def setup_logging(settings: Settings) -> logging.handlers.QueueListener:
    """Configure asynchronous logging using a queue-based pipeline."""
    global _listener

    if _listener is not None:
        return _listener

    os.makedirs(settings.log_dir, exist_ok=True)
    log_path = Path(settings.log_dir) / settings.log_file

    queue_handler = logging.handlers.QueueHandler(_log_queue)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(settings.log_level.upper())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(settings.log_level.upper())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(settings.log_level.upper())
    root_logger.addHandler(queue_handler)

    listener = logging.handlers.QueueListener(
        _log_queue,
        file_handler,
        console_handler,
        respect_handler_level=True,
    )
    listener.start()

    def shutdown_logging() -> None:
        listener.stop()
        for handler in (file_handler, console_handler):
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass

    atexit.register(shutdown_logging)
    _listener = listener
    return listener
