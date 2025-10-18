import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings

logger = logging.getLogger(__name__)


def build_http_session(settings: Settings) -> requests.Session:
    """Create a globally shared HTTP session with connection pooling."""
    session = requests.Session()

    retry_strategy = Retry(
        total=settings.http_max_retries,
        backoff_factor=settings.http_backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"}),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        pool_connections=settings.http_pool_connections,
        pool_maxsize=settings.http_pool_maxsize,
        max_retries=retry_strategy,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "ForestFireDetection/1.0"})
    session.max_redirects = 5

    logger.debug(
        "Configured HTTP session: pool_connections=%s, pool_maxsize=%s, retries=%s",
        settings.http_pool_connections,
        settings.http_pool_maxsize,
        settings.http_max_retries,
    )

    return session
