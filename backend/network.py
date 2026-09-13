"""Lightweight internet reachability probe for model defaulting."""

from __future__ import annotations

import logging
import os
import socket
import time

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 15.0
_cache_at: float = 0.0
_cache_value: bool | None = None

_PROBE_HOSTS = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
)


def clear_network_cache() -> None:
    global _cache_at, _cache_value
    _cache_at = 0.0
    _cache_value = None


def network_available(*, timeout: float = 1.0, force: bool = False) -> bool:
    """
    Return True when the internet appears reachable.

    Honors MARVIN_NETWORK_AVAILABLE=0|1 for tests. Results are cached briefly
    so resolve_active_selection does not probe every turn.
    """
    global _cache_at, _cache_value

    override = (os.environ.get("MARVIN_NETWORK_AVAILABLE") or "").strip().lower()
    if override in {"0", "false", "no", "off"}:
        return False
    if override in {"1", "true", "yes", "on"}:
        return True

    now = time.monotonic()
    if (
        not force
        and _cache_value is not None
        and (now - _cache_at) < _CACHE_TTL_SECONDS
    ):
        return _cache_value

    available = False
    for host, port in _PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                available = True
                break
        except OSError:
            continue

    _cache_value = available
    _cache_at = now
    if not available:
        logger.info("NETWORK: reachability probe failed — treating as offline")
    return available
