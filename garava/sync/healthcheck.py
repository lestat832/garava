"""Healthcheck ping for sync health monitoring."""

from __future__ import annotations

import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


def ping_healthcheck(url: str, fail: bool = False) -> None:
    """Ping a healthchecks.io-compatible URL to report sync status.

    Args:
        url: Base ping URL (e.g., https://hc-ping.com/<uuid>)
        fail: If True, appends /fail to signal a failure
    """
    if not url:
        return

    target = f"{url.rstrip('/')}/fail" if fail else url

    try:
        req = Request(target, method="GET")
        with urlopen(req, timeout=TIMEOUT_SECONDS):
            pass
        logger.debug(f"Healthcheck ping {'fail' if fail else 'ok'}: {target}")
    except (URLError, OSError) as e:
        logger.warning(f"Healthcheck ping failed: {e}")
