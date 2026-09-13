"""Secure credential storage — macOS Keychain in production, env fallback for dev."""

from __future__ import annotations

import logging
import os
import re
from typing import Literal

logger = logging.getLogger(__name__)

ProviderId = Literal["openai", "anthropic", "xai"]

_SERVICE = "Marvin AI Providers"
_ACCOUNT = {
    "openai": "openai-api-key",
    "anthropic": "anthropic-api-key",
    "xai": "xai-api-key",
}
_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
}

_KEY_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|xai-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,})",
    re.I,
)

_memory: dict[str, str] = {}


def redact_secrets(text: str) -> str:
    if not text:
        return text
    return _KEY_PATTERN.sub("[REDACTED]", text)


class CredentialStore:
    """Isolated per-provider API key storage."""

    def get(self, provider_id: ProviderId) -> str | None:
        if provider_id in _memory:
            return _memory[provider_id]
        try:
            import keyring

            value = keyring.get_password(_SERVICE, _ACCOUNT[provider_id])
            if value:
                _memory[provider_id] = value
                return value
        except Exception:
            logger.debug("Keychain read failed for %s", provider_id, exc_info=True)
        env_name = _ENV[provider_id]
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            _memory[provider_id] = env_value
            return env_value
        return None

    def set(self, provider_id: ProviderId, api_key: str) -> None:
        cleaned = (api_key or "").strip()
        if not cleaned:
            raise ValueError("API key cannot be empty")
        try:
            import keyring

            keyring.set_password(_SERVICE, _ACCOUNT[provider_id], cleaned)
        except Exception:
            logger.exception("Keychain write failed for %s", provider_id)
            raise RuntimeError(
                "Could not store the API key in the system keychain."
            ) from None
        _memory[provider_id] = cleaned
        logger.info("CREDENTIALS: saved provider=%s", provider_id)

    def delete(self, provider_id: ProviderId) -> None:
        try:
            import keyring

            try:
                keyring.delete_password(_SERVICE, _ACCOUNT[provider_id])
            except keyring.errors.PasswordDeleteError:
                pass
        except Exception:
            logger.debug("Keychain delete failed for %s", provider_id, exc_info=True)
        _memory.pop(provider_id, None)
        logger.info("CREDENTIALS: deleted provider=%s", provider_id)

    def is_configured(self, provider_id: ProviderId) -> bool:
        return bool(self.get(provider_id))

    def clear_memory(self) -> None:
        _memory.clear()


_STORE: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    global _STORE
    if _STORE is None:
        _STORE = CredentialStore()
    return _STORE
