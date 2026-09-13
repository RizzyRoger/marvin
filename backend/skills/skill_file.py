"""Skill file service — placeholder skill.md for future user-defined skills."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from backend.config import ROOT

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = ROOT / "resources" / "defaults" / "skill.md"
_PLACEHOLDER = (
    "# Marvin Skill\n\n"
    "This file is reserved for future user-defined Marvin skills.\n\n"
    "No custom skill is configured yet.\n"
)


def _app_support_dir() -> Path:
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return base / "Marvin"
    try:
        sysname = os.uname().sysname
    except AttributeError:
        sysname = ""
    if sysname == "Darwin" or (home / "Library" / "Application Support").is_dir():
        return home / "Library" / "Application Support" / "Marvin"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "Marvin"


class SkillFileService:
    """Locate and ensure the runtime skill.md without overwriting user edits."""

    def __init__(self, runtime_root: Path | None = None):
        self._root = runtime_root or (_app_support_dir() / "skills")
        self._path = self._root / "skill.md"

    def get_path(self) -> Path:
        return self._path

    def get_status(self) -> dict:
        exists = self._path.is_file()
        configured = False
        if exists:
            try:
                configured = self._path.read_text(encoding="utf-8") != _PLACEHOLDER
            except OSError:
                configured = True
        return {
            "path": str(self._path),
            "exists": exists,
            "configured": configured,
        }

    def ensure_exists(self) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            return self._path
        source = _DEFAULT_TEMPLATE if _DEFAULT_TEMPLATE.is_file() else None
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix="skill-", suffix=".md", dir=str(self._root)
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                if source is not None:
                    handle.write(source.read_text(encoding="utf-8"))
                else:
                    handle.write(_PLACEHOLDER)
            os.replace(tmp_name, self._path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        logger.info("SKILL: created placeholder at %s", self._path)
        return self._path

    def read(self) -> str:
        self.ensure_exists()
        return self._path.read_text(encoding="utf-8")


_SERVICE: SkillFileService | None = None


def get_skill_file_service() -> SkillFileService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = SkillFileService()
    return _SERVICE
