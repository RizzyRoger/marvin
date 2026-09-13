"""Spotify capability registration, schemas, and dispatch."""

from __future__ import annotations

import logging
import threading
from typing import Any

from backend.config import SPOTIFY_CLIENT_ID, SPOTIFY_ENABLED
from backend.credentials.spotify_store import get_spotify_credential_store
from backend.tools.spotify import client as spotify_client
from backend.tools.spotify.auth import (
    build_authorize_url,
    disconnect_spotify,
    spotify_client_configured,
)
from backend.tools.spotify.types import (
    SpotifyError,
    SpotifyErrorCategory,
    SpotifyStatus,
)

logger = logging.getLogger(__name__)

_capability_available = False

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "spotify_now_playing",
            "description": (
                "Get the user's currently playing Spotify track and playback state."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_playback",
            "description": (
                "Control Spotify Connect playback: play/resume/unpause/continue, pause, "
                "next, previous, or set volume_percent (0-100). Map unpause or continue "
                "to action resume."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "play",
                            "resume",
                            "pause",
                            "next",
                            "skip",
                            "previous",
                            "back",
                            "volume",
                        ],
                        "description": (
                            "Use resume for unpause/continue; pause to pause; "
                            "next/skip and previous/back for track changes."
                        ),
                    },
                    "volume_percent": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Required when action is volume.",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_search_play",
            "description": (
                "Search Spotify and start playback of the best matching track, album, "
                "playlist, or artist. For playlists, checks the user’s library titles "
                "first, then public catalog. Never invent a substitute title if the "
                "requested item cannot be played."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Song, artist, album, or playlist to play. For personal "
                            "playlists use the playlist name (e.g. Workout)."
                        ),
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["auto", "track", "album", "playlist", "artist"],
                        "description": (
                            "Content type. Prefer auto when unsure — Marvin ranks "
                            "albums/artists/tracks using the user’s top listening. "
                            "Use album/playlist/artist/track when the user is explicit."
                        ),
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


def register_spotify_capability() -> bool:
    global _capability_available
    _capability_available = (
        SPOTIFY_ENABLED
        and spotify_client_configured()
        and get_spotify_credential_store().is_connected()
    )
    return _capability_available


def spotify_is_available() -> bool:
    return _capability_available or register_spotify_capability()


def spotify_status() -> SpotifyStatus:
    configured = spotify_client_configured()
    connected = get_spotify_credential_store().is_connected()
    tokens = get_spotify_credential_store().get() if connected else None
    hint = ""
    if not SPOTIFY_ENABLED:
        hint = "Spotify integration is disabled."
    elif not configured:
        hint = "Set SPOTIFY_CLIENT_ID in the environment to enable Connect Spotify."
    elif not connected:
        hint = "Connect Spotify to control playback. Premium and an open Spotify app are required."
    elif tokens and tokens.api_warning:
        hint = tokens.api_warning
    elif tokens and "playlist-read-private" not in (tokens.scope or ""):
        hint = (
            "Connected, but playlist library access needs a reconnect. "
            "Click Reconnect Spotify so Marvin can find your playlists."
        )
    else:
        hint = "Connected. Playback uses Spotify Connect on your open Spotify devices."
    return SpotifyStatus(
        enabled=SPOTIFY_ENABLED,
        client_configured=configured,
        connected=connected,
        display_name=(tokens.display_name if tokens else ""),
        hint=hint,
    )


def tools_for_spotify() -> list[dict[str, Any]]:
    if not spotify_is_available():
        return []
    return list(TOOL_DEFINITIONS)


def wrap_spotify_result(text: str) -> str:
    return f'<spotify_data untrusted="true">\n{text}\n</spotify_data>'


def user_facing_error(exc: SpotifyError) -> str:
    return exc.user_message()


def begin_authorize() -> dict[str, str]:
    return build_authorize_url()


def disconnect() -> SpotifyStatus:
    disconnect_spotify()
    register_spotify_capability()
    return spotify_status()


def dispatch_spotify_tool(
    name: str,
    args: dict,
    user_message: str,
    *,
    cancellation_event: threading.Event | None = None,
) -> str:
    del user_message  # reserved for future context-aware disambiguation
    if cancellation_event is not None and cancellation_event.is_set():
        raise SpotifyError(SpotifyErrorCategory.CANCELED, "Spotify request canceled.")
    if not spotify_is_available():
        status = spotify_status()
        if not status.client_configured:
            raise SpotifyError(
                SpotifyErrorCategory.NOT_CONFIGURED,
                "Spotify isn’t configured. Set SPOTIFY_CLIENT_ID and restart Marvin.",
            )
        raise SpotifyError(
            SpotifyErrorCategory.NOT_CONNECTED,
            "Spotify isn’t connected. Open Settings to connect.",
        )

    try:
        if name == "spotify_now_playing":
            info = spotify_client.get_now_playing()
            if cancellation_event is not None and cancellation_event.is_set():
                raise SpotifyError(
                    SpotifyErrorCategory.CANCELED, "Spotify request canceled."
                )
            if not info.get("name"):
                text = "Nothing is currently playing on Spotify."
            else:
                state = "Playing" if info.get("is_playing") else "Paused"
                artists = info.get("artists") or "unknown artist"
                text = f"{state}: {info['name']} by {artists}."
            return wrap_spotify_result(text)

        if name == "spotify_playback":
            action = str(args.get("action") or "")
            volume = args.get("volume_percent")
            volume_int = int(volume) if volume is not None else None
            text = spotify_client.playback_action(action, volume_percent=volume_int)
            if cancellation_event is not None and cancellation_event.is_set():
                raise SpotifyError(
                    SpotifyErrorCategory.CANCELED, "Spotify request canceled."
                )
            return wrap_spotify_result(text)

        if name == "spotify_search_play":
            query = str(args.get("query") or "")
            kind = str(args.get("kind") or "auto")
            text = spotify_client.search_and_play(query, kind=kind)
            if cancellation_event is not None and cancellation_event.is_set():
                raise SpotifyError(
                    SpotifyErrorCategory.CANCELED, "Spotify request canceled."
                )
            return wrap_spotify_result(text)

        raise SpotifyError(
            SpotifyErrorCategory.API,
            f"Unknown Spotify tool: {name}",
        )
    except SpotifyError:
        raise
    except Exception as exc:
        logger.exception("SPOTIFY: tool failed name=%s", name)
        raise SpotifyError(
            SpotifyErrorCategory.UNKNOWN,
            "Spotify could not complete that request.",
        ) from exc
