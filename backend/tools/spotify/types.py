"""Spotify tool types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SpotifyDecision(str, Enum):
    REQUIRED = "required"
    NOT_NEEDED = "not_needed"
    UNAVAILABLE = "unavailable"


class SpotifyErrorCategory(str, Enum):
    NOT_CONNECTED = "not_connected"
    NOT_CONFIGURED = "not_configured"
    NO_DEVICE = "no_device"
    PREMIUM_REQUIRED = "premium_required"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    NETWORK = "network"
    CANCELED = "canceled"
    API = "api"
    UNKNOWN = "unknown"


class SpotifyError(Exception):
    def __init__(self, category: SpotifyErrorCategory | str, message: str):
        super().__init__(message)
        self.category = (
            category
            if isinstance(category, SpotifyErrorCategory)
            else SpotifyErrorCategory(category)
        )
        self.message = message

    def user_message(self) -> str:
        return self.message


@dataclass
class SpotifyStatus:
    enabled: bool
    client_configured: bool
    connected: bool
    display_name: str = ""
    hint: str = ""
