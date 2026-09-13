"""Persisted toggles for bundled Marvin skills (Obsidian formats + feature skills)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from backend.skills.library import BUNDLED_SKILL_IDS, default_enabled_map
from backend.skills.skill_file import _app_support_dir

logger = logging.getLogger(__name__)

_SETTINGS_NAME = "bundled_skills.json"
_LEGACY_SETTINGS_NAME = "format_skills.json"


def _settings_path() -> Path:
    return _app_support_dir() / "skills" / _SETTINGS_NAME


def _legacy_settings_path() -> Path:
    return _app_support_dir() / "skills" / _LEGACY_SETTINGS_NAME


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("SKILL: could not read skill settings %s", path)
        return None
    return raw if isinstance(raw, dict) else None


def _known_skill_ids() -> tuple[str, ...]:
    try:
        from backend.skills.library import discover_bundled_skills

        extra = tuple(skill.skill_id for skill in discover_bundled_skills())
    except Exception:
        extra = ()
    seen: list[str] = []
    for skill_id in (*BUNDLED_SKILL_IDS, *extra):
        if skill_id not in seen:
            seen.append(skill_id)
    return tuple(seen)


def load_format_skill_settings() -> dict[str, bool]:
    """Load bundled skill toggles (name kept for API compatibility)."""
    defaults = default_enabled_map()
    raw = _read_json(_settings_path())
    if raw is None:
        raw = _read_json(_legacy_settings_path())
    merged = dict(defaults)
    for skill_id in _known_skill_ids():
        if skill_id not in merged:
            merged[skill_id] = True
        if raw and skill_id in raw:
            merged[skill_id] = bool(raw[skill_id])
    return merged


def save_format_skill_settings(enabled: dict[str, bool]) -> dict[str, bool]:
    """Persist bundled skill toggles to bundled_skills.json."""
    merged = load_format_skill_settings()
    for skill_id in _known_skill_ids():
        if skill_id in enabled:
            merged[skill_id] = bool(enabled[skill_id])
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(merged, indent=2, sort_keys=True) + "\n"
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix="bundled-skills-", suffix=".json", dir=str(path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        Path(tmp_name).replace(path)
    except Exception:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    logger.info("SKILL: saved bundled skill settings %s", merged)
    return merged


# Preferred aliases
load_bundled_skill_settings = load_format_skill_settings
save_bundled_skill_settings = save_format_skill_settings
