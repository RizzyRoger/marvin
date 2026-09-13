"""User prefs for Marvin spoken output (TTS voice + when to speak)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, MODELS_DIR, PIPER_VOICE

logger = logging.getLogger(__name__)

_PREFS_PATH = DATA_DIR / "speech_prefs.json"

# Piper voices: nationality × gender → voice id / relative path under models/piper
PIPER_VOICE_CATALOG: dict[str, dict[str, dict[str, str]]] = {
    "british": {
        "male": {
            "id": "en_GB-alan-medium",
            "rel": "en/en_GB/alan/medium",
        },
        "female": {
            "id": "en_GB-alba-medium",
            "rel": "en/en_GB/alba/medium",
        },
    },
    "american": {
        "male": {
            "id": "en_US-danny-low",
            "rel": "en/en_US/danny/low",
        },
        "female": {
            "id": "en_US-lessac-medium",
            "rel": "en/en_US/lessac/medium",
        },
    },
}

SPEECH_MODES = ("always_on", "voice_input_only", "always_off")


@dataclass
class SpeechSettings:
    nationality: str = "british"
    gender: str = "male"
    mode: str = "always_on"  # always_on | voice_input_only | always_off


def _defaults() -> SpeechSettings:
    return SpeechSettings()


def load_speech_settings() -> SpeechSettings:
    try:
        if _PREFS_PATH.is_file():
            import json

            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                nat = str(data.get("nationality") or "british").lower()
                gen = str(data.get("gender") or "male").lower()
                mode = str(data.get("mode") or "always_on").lower()
                if nat not in PIPER_VOICE_CATALOG:
                    nat = "british"
                if gen not in PIPER_VOICE_CATALOG[nat]:
                    gen = "male"
                if mode not in SPEECH_MODES:
                    mode = "always_on"
                return SpeechSettings(nationality=nat, gender=gen, mode=mode)
    except (OSError, ValueError, TypeError):
        logger.debug("SPEECH: prefs load failed", exc_info=True)
    return _defaults()


def save_speech_settings(
    *,
    nationality: str | None = None,
    gender: str | None = None,
    mode: str | None = None,
) -> SpeechSettings:
    current = load_speech_settings()
    nat = (nationality or current.nationality).lower()
    gen = (gender or current.gender).lower()
    md = (mode or current.mode).lower()
    if nat not in PIPER_VOICE_CATALOG:
        raise ValueError("nationality must be british or american")
    if gen not in PIPER_VOICE_CATALOG[nat]:
        raise ValueError("gender must be male or female")
    if md not in SPEECH_MODES:
        raise ValueError("mode must be always_on, voice_input_only, or always_off")
    settings = SpeechSettings(nationality=nat, gender=gen, mode=md)
    import json

    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(
        json.dumps(
            {
                "nationality": settings.nationality,
                "gender": settings.gender,
                "mode": settings.mode,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return settings


def preferred_piper_paths(
    settings: SpeechSettings | None = None,
) -> tuple[str, Path, Path]:
    """Return the user-selected voice paths (may not be downloaded yet)."""
    settings = settings or load_speech_settings()
    entry = PIPER_VOICE_CATALOG[settings.nationality][settings.gender]
    voice_id = entry["id"]
    model_dir = MODELS_DIR / "piper" / entry["rel"]
    onnx = model_dir / f"{voice_id}.onnx"
    cfg = model_dir / f"{voice_id}.onnx.json"
    return voice_id, onnx, cfg


def resolve_piper_voice(
    settings: SpeechSettings | None = None,
) -> tuple[str, Path, Path]:
    """Return loadable (voice_id, onnx_path, config_path), falling back to Alan."""
    voice_id, onnx, cfg = preferred_piper_paths(settings)
    if onnx.is_file() and cfg.is_file():
        return voice_id, onnx, cfg
    from backend.config import PIPER_CONFIG_PATH, PIPER_MODEL_PATH

    if PIPER_MODEL_PATH.is_file():
        return PIPER_VOICE, PIPER_MODEL_PATH, PIPER_CONFIG_PATH
    return voice_id, onnx, cfg


def speech_settings_payload() -> dict[str, Any]:
    settings = load_speech_settings()
    preferred_id, preferred_onnx, _cfg = preferred_piper_paths(settings)
    active_id, _onnx, _active_cfg = resolve_piper_voice(settings)
    return {
        "nationality": settings.nationality,
        "gender": settings.gender,
        "mode": settings.mode,
        "voice_id": preferred_id,
        "active_voice_id": active_id,
        "voice_ready": preferred_onnx.is_file(),
        "nationalities": list(PIPER_VOICE_CATALOG.keys()),
        "genders": ["male", "female"],
        "modes": list(SPEECH_MODES),
    }
