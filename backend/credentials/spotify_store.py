"""Spotify OAuth token storage in the system keychain."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

_SERVICE = "Marvin Spotify"
_ACCOUNT = "spotify-oauth-tokens"
_memory: dict | None = None


@dataclass
class SpotifyTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp
    token_type: str = "Bearer"
    scope: str = ""
    display_name: str = ""
    # Non-secret Settings hint when profile/API probe failed after login.
    api_warning: str = ""

    def is_expired(self, *, skew_seconds: float = 60.0) -> bool:
        return time.time() >= (self.expires_at - skew_seconds)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "SpotifyTokens":
        data = json.loads(raw)
        return cls(
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_at=float(data.get("expires_at") or 0),
            token_type=str(data.get("token_type") or "Bearer"),
            scope=str(data.get("scope") or ""),
            display_name=str(data.get("display_name") or ""),
            api_warning=str(data.get("api_warning") or ""),
        )


class SpotifyCredentialStore:
    """Store Spotify OAuth tokens separately from AI provider keys."""

    def get(self) -> SpotifyTokens | None:
        global _memory
        if _memory is not None:
            try:
                return SpotifyTokens.from_json(json.dumps(_memory))
            except Exception:
                _memory = None
        try:
            import keyring

            raw = keyring.get_password(_SERVICE, _ACCOUNT)
            if not raw:
                return None
            tokens = SpotifyTokens.from_json(raw)
            _memory = asdict(tokens)
            return tokens
        except Exception:
            logger.debug("Spotify Keychain read failed", exc_info=True)
            return None

    def set(self, tokens: SpotifyTokens) -> None:
        global _memory
        if not tokens.access_token:
            raise ValueError("access_token required")
        try:
            import keyring

            keyring.set_password(_SERVICE, _ACCOUNT, tokens.to_json())
        except Exception:
            logger.exception("Spotify Keychain write failed")
            raise RuntimeError(
                "Could not store Spotify tokens in the system keychain."
            ) from None
        _memory = asdict(tokens)
        logger.info("CREDENTIALS: saved spotify oauth tokens")

    def delete(self) -> None:
        global _memory
        try:
            import keyring

            try:
                keyring.delete_password(_SERVICE, _ACCOUNT)
            except keyring.errors.PasswordDeleteError:
                pass
        except Exception:
            logger.debug("Spotify Keychain delete failed", exc_info=True)
        _memory = None
        logger.info("CREDENTIALS: deleted spotify oauth tokens")

    def is_connected(self) -> bool:
        tokens = self.get()
        return bool(tokens and tokens.refresh_token)

    def clear_memory(self) -> None:
        global _memory
        _memory = None


_SPOTIFY_STORE: SpotifyCredentialStore | None = None


def get_spotify_credential_store() -> SpotifyCredentialStore:
    global _SPOTIFY_STORE
    if _SPOTIFY_STORE is None:
        _SPOTIFY_STORE = SpotifyCredentialStore()
    return _SPOTIFY_STORE
