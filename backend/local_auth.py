"""Per-install local API authentication (Keychain-backed)."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

_SERVICE = "Marvin Local API"
_ACCOUNT = "session-token"
_COOKIE = "marvin_token"
_HEADER = "X-Marvin-Token"
_memory_token: str | None = None


def auth_enabled() -> bool:
    """Require auth in bundled apps; override with MARVIN_REQUIRE_AUTH."""
    override = (os.environ.get("MARVIN_REQUIRE_AUTH") or "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    return (os.environ.get("MARVIN_BUNDLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def get_or_create_token() -> str:
    """Return the install token, creating and storing it in Keychain when needed."""
    global _memory_token
    if _memory_token:
        return _memory_token

    env_token = (os.environ.get("MARVIN_API_TOKEN") or "").strip()
    if env_token:
        _memory_token = env_token
        return _memory_token

    try:
        import keyring

        existing = keyring.get_password(_SERVICE, _ACCOUNT)
        if existing:
            _memory_token = existing
            return _memory_token
        token = secrets.token_urlsafe(32)
        keyring.set_password(_SERVICE, _ACCOUNT, token)
        _memory_token = token
        logger.info("AUTH: created local API token in Keychain")
        return _memory_token
    except Exception:
        logger.warning("AUTH: Keychain unavailable — using process-local token", exc_info=True)
        _memory_token = secrets.token_urlsafe(32)
        return _memory_token


def token_matches(candidate: Optional[str]) -> bool:
    if not candidate:
        return False
    expected = get_or_create_token()
    return secrets.compare_digest(candidate.strip(), expected)


def extract_token_from_headers(authorization: Optional[str], x_token: Optional[str]) -> Optional[str]:
    if x_token and x_token.strip():
        return x_token.strip()
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        if len(parts) == 1:
            return parts[0].strip()
    return None


COOKIE_NAME = _COOKIE
HEADER_NAME = _HEADER
