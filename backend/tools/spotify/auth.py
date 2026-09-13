"""Spotify OAuth PKCE helpers."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
import urllib.parse
from typing import Any

import httpx

from backend.config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_SCOPES,
)
from backend.credentials.spotify_store import (
    SpotifyTokens,
    get_spotify_credential_store,
)
from backend.tools.spotify.types import SpotifyError, SpotifyErrorCategory

logger = logging.getLogger(__name__)

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"

_pending_lock = threading.Lock()
_pending: dict[str, str] = {}  # state -> code_verifier


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _new_verifier() -> str:
    return _b64url(secrets.token_bytes(64))


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def spotify_client_configured() -> bool:
    return bool(SPOTIFY_CLIENT_ID)


def build_authorize_url() -> dict[str, str]:
    if not SPOTIFY_CLIENT_ID:
        raise SpotifyError(
            SpotifyErrorCategory.NOT_CONFIGURED,
            "Spotify is not configured. Set SPOTIFY_CLIENT_ID in the environment.",
        )
    verifier = _new_verifier()
    state = secrets.token_urlsafe(24)
    with _pending_lock:
        _pending[state] = verifier
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": _challenge(verifier),
    }
    url = f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"
    logger.info("SPOTIFY: authorize_url_created")
    return {"authorize_url": url, "state": state, "redirect_uri": SPOTIFY_REDIRECT_URI}


def exchange_code(code: str, state: str) -> SpotifyTokens:
    with _pending_lock:
        verifier = _pending.pop(state, None)
    if not verifier:
        raise SpotifyError(
            SpotifyErrorCategory.AUTH,
            "Spotify login state expired. Start Connect Spotify again.",
        )
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "code_verifier": verifier,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(_TOKEN_URL, data=data)
            payload = response.json()
            if response.status_code >= 400:
                raise SpotifyError(
                    SpotifyErrorCategory.AUTH,
                    "Spotify rejected the login. Try connecting again.",
                )
    except SpotifyError:
        raise
    except Exception as exc:
        raise SpotifyError(
            SpotifyErrorCategory.NETWORK,
            "Could not reach Spotify to finish login.",
        ) from exc

    tokens = SpotifyTokens(
        access_token=str(payload.get("access_token") or ""),
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_at=time.time() + float(payload.get("expires_in") or 3600),
        token_type=str(payload.get("token_type") or "Bearer"),
        scope=str(payload.get("scope") or ""),
    )
    if not tokens.access_token or not tokens.refresh_token:
        raise SpotifyError(
            SpotifyErrorCategory.AUTH,
            "Spotify login did not return usable tokens.",
        )
    # Best-effort profile name for Settings status.
    try:
        profile = spotify_api_request("GET", "/me", tokens=tokens, refresh=False)
        tokens.display_name = str(profile.get("display_name") or "")
        tokens.api_warning = ""
    except SpotifyError as exc:
        logger.warning(
            "SPOTIFY: profile fetch after login failed category=%s message=%s",
            exc.category.value,
            exc.message,
        )
        tokens.api_warning = (
            "Connected, but Spotify blocked the profile check. In the Developer "
            "Dashboard, add this account under User Management, confirm the app "
            "owner has Premium, then reconnect if playback fails."
        )
    except Exception:
        logger.warning("SPOTIFY: profile fetch after login failed", exc_info=True)
        tokens.api_warning = (
            "Connected, but Spotify blocked the profile check. In the Developer "
            "Dashboard, add this account under User Management, confirm the app "
            "owner has Premium, then reconnect if playback fails."
        )
    get_spotify_credential_store().set(tokens)
    logger.info("SPOTIFY: connected")
    return tokens


def refresh_access_token(tokens: SpotifyTokens | None = None) -> SpotifyTokens:
    store = get_spotify_credential_store()
    current = tokens or store.get()
    if current is None or not current.refresh_token:
        raise SpotifyError(
            SpotifyErrorCategory.NOT_CONNECTED,
            "Spotify isn’t connected. Open Settings to connect.",
        )
    data = {
        "grant_type": "refresh_token",
        "refresh_token": current.refresh_token,
        "client_id": SPOTIFY_CLIENT_ID,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(_TOKEN_URL, data=data)
            payload = response.json()
            if response.status_code >= 400:
                store.delete()
                raise SpotifyError(
                    SpotifyErrorCategory.AUTH,
                    "Spotify session expired. Open Settings to reconnect.",
                )
    except SpotifyError:
        raise
    except Exception as exc:
        raise SpotifyError(
            SpotifyErrorCategory.NETWORK,
            "Could not refresh the Spotify session.",
        ) from exc

    updated = SpotifyTokens(
        access_token=str(payload.get("access_token") or ""),
        refresh_token=str(payload.get("refresh_token") or current.refresh_token),
        expires_at=time.time() + float(payload.get("expires_in") or 3600),
        token_type=str(payload.get("token_type") or "Bearer"),
        scope=str(payload.get("scope") or current.scope),
        display_name=current.display_name,
    )
    if not updated.access_token:
        raise SpotifyError(
            SpotifyErrorCategory.AUTH,
            "Spotify refresh failed. Open Settings to reconnect.",
        )
    store.set(updated)
    return updated


def get_valid_tokens() -> SpotifyTokens:
    store = get_spotify_credential_store()
    tokens = store.get()
    if tokens is None:
        raise SpotifyError(
            SpotifyErrorCategory.NOT_CONNECTED,
            "Spotify isn’t connected. Open Settings to connect.",
        )
    if tokens.is_expired():
        return refresh_access_token(tokens)
    return tokens


def disconnect_spotify() -> None:
    get_spotify_credential_store().delete()
    with _pending_lock:
        _pending.clear()
    logger.info("SPOTIFY: disconnected")


def spotify_api_request(
    method: str,
    path: str,
    *,
    tokens: SpotifyTokens | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    refresh: bool = True,
) -> Any:
    current = tokens or get_valid_tokens()
    headers = {"Authorization": f"{current.token_type} {current.access_token}"}
    url = path if path.startswith("http") else f"{_API_BASE}{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
            )
            if response.status_code == 401 and refresh:
                current = refresh_access_token(current)
                headers = {
                    "Authorization": f"{current.token_type} {current.access_token}"
                }
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
            if response.status_code == 204:
                return {}
            if response.status_code == 404 and "player" in path:
                # Client code re-checks /me/player/devices and remaps: empty → NO_DEVICE,
                # devices present but start failed → clearer API message.
                raise SpotifyError(
                    SpotifyErrorCategory.NO_DEVICE,
                    "Spotify player endpoint returned 404.",
                )
            if response.status_code == 403:
                body = ""
                try:
                    body = (response.text or "")[:300]
                except Exception:
                    body = ""
                body_l = body.lower()
                logger.warning(
                    "SPOTIFY: api 403 path=%s body=%s",
                    path,
                    body.replace("\n", " "),
                )
                if "premium" in body_l:
                    raise SpotifyError(
                        SpotifyErrorCategory.PREMIUM_REQUIRED,
                        "Spotify Premium is required for playback control.",
                    )
                if "not been approved" in body_l or "not registered" in body_l:
                    raise SpotifyError(
                        SpotifyErrorCategory.AUTH,
                        "This Spotify account is not approved for the Marvin app. "
                        "Add it under User Management in the Spotify Developer Dashboard.",
                    )
                raise SpotifyError(
                    SpotifyErrorCategory.API,
                    "Spotify refused that action.",
                )
            if response.status_code == 429:
                raise SpotifyError(
                    SpotifyErrorCategory.RATE_LIMITED,
                    "Spotify rate-limited the request. Try again shortly.",
                )
            if response.status_code >= 400:
                raise SpotifyError(
                    SpotifyErrorCategory.API,
                    "Spotify returned an error for that request.",
                )
            if not response.content:
                return {}
            return response.json()
    except SpotifyError:
        raise
    except Exception as exc:
        raise SpotifyError(
            SpotifyErrorCategory.NETWORK,
            "Could not reach Spotify.",
        ) from exc
