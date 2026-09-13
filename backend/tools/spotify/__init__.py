"""Spotify Connect control tools for Marvin."""

from backend.tools.spotify.routing import (
    decide_spotify,
    looks_like_deferred_spotify,
    looks_like_invented_spotify_claim,
    prefer_spotify_tool_truth,
    unwrap_spotify_tool_text,
)
from backend.tools.spotify.service import (
    TOOL_DEFINITIONS,
    begin_authorize,
    disconnect,
    dispatch_spotify_tool,
    register_spotify_capability,
    spotify_is_available,
    spotify_status,
    tools_for_spotify,
    user_facing_error,
    wrap_spotify_result,
)
from backend.tools.spotify.types import (
    SpotifyDecision,
    SpotifyError,
    SpotifyErrorCategory,
    SpotifyStatus,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "SpotifyDecision",
    "SpotifyError",
    "SpotifyErrorCategory",
    "SpotifyStatus",
    "begin_authorize",
    "decide_spotify",
    "looks_like_deferred_spotify",
    "looks_like_invented_spotify_claim",
    "prefer_spotify_tool_truth",
    "unwrap_spotify_tool_text",
    "disconnect",
    "dispatch_spotify_tool",
    "register_spotify_capability",
    "spotify_is_available",
    "spotify_status",
    "tools_for_spotify",
    "user_facing_error",
    "wrap_spotify_result",
]
