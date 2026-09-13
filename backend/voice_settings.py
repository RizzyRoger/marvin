"""Persisted Voice & Listening / Voice Lock settings."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

_SETTINGS_PATH = DATA_DIR / "voice_listening_settings.json"
_LOCK = threading.Lock()


@dataclass
class VoiceListeningSettings:
    voice_lock_enabled: bool = False
    voice_profile_id: str = "primary"
    voice_profile_status: str = "not_configured"  # not_configured|enabled|disabled|needs_reenrollment|error
    strictness_mode: str = "strict"  # balanced|strict|very_strict
    require_addressing: bool = True
    contextual_continuation_enabled: bool = True
    continuation_window_seconds: int = 60
    verifier_model_version: str = ""
    enrollment_completed_at: str = ""
    preferred_microphone_id: str = ""
    profile_name: str = "Primary user"


def default_settings() -> VoiceListeningSettings:
    return VoiceListeningSettings()


def load_voice_settings() -> VoiceListeningSettings:
    with _LOCK:
        if not _SETTINGS_PATH.is_file():
            return default_settings()
        try:
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_settings()
    base = asdict(default_settings())
    base.update({k: v for k, v in data.items() if k in base})
    # Clamp continuation window.
    try:
        base["continuation_window_seconds"] = int(
            max(30, min(120, int(base["continuation_window_seconds"])))
        )
    except (TypeError, ValueError):
        base["continuation_window_seconds"] = 60
    if base.get("strictness_mode") not in {"balanced", "strict", "very_strict"}:
        base["strictness_mode"] = "strict"
    return VoiceListeningSettings(**base)


def save_voice_settings(settings: VoiceListeningSettings) -> VoiceListeningSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    with _LOCK:
        _SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(
        "VOICE_SETTINGS: saved enabled=%s status=%s strictness=%s",
        settings.voice_lock_enabled,
        settings.voice_profile_status,
        settings.strictness_mode,
    )
    return settings


def update_voice_settings(**changes) -> VoiceListeningSettings:
    current = load_voice_settings()
    data = asdict(current)
    data.update({k: v for k, v in changes.items() if k in data and v is not None})
    return save_voice_settings(VoiceListeningSettings(**data))
