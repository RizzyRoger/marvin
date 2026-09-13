"""User-created SKILL.md files under Application Support."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from backend.skills.library import BundledSkill, _parse_frontmatter
from backend.skills.skill_file import _app_support_dir

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")


def custom_skills_root() -> Path:
    return _app_support_dir() / "skills" / "custom"


def _safe_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (raw or "").strip().lower()).strip("-")
    return slug[:48]


def custom_skill_exists(slug: str) -> bool:
    safe = _safe_slug(slug)
    if not safe:
        return False
    return (custom_skills_root() / safe / "SKILL.md").is_file()


def discover_custom_skills() -> list[BundledSkill]:
    root = custom_skills_root()
    if not root.is_dir():
        return []
    found: list[BundledSkill] = []
    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            logger.exception("SKILL: failed to read custom skill %s", path)
            continue
        meta, body = _parse_frontmatter(raw)
        found.append(
            BundledSkill(
                skill_id=skill_dir.name,
                name=meta.get("name") or skill_dir.name,
                description=meta.get("description") or "",
                body=body,
                path=path,
                phase=1,
                group="custom",
            )
        )
    return found


def save_custom_skill(
    slug: str,
    name: str,
    description: str,
    body: str,
    *,
    overwrite: bool = False,
    authorized: bool = False,
) -> str:
    """Write a custom SKILL.md. Requires explicit authorization."""
    if not authorized:
        return "REFUSED: saving a skill requires explicit user authorization."
    safe = _safe_slug(slug or name)
    if not safe or not _SLUG_RE.match(safe):
        return "REFUSED: skill id must be a short lowercase slug."
    if "projects" in safe:
        return "REFUSED: cannot create a skill for the Projects folder."
    dest_dir = custom_skills_root() / safe
    dest = dest_dir / "SKILL.md"
    if dest.exists() and not overwrite:
        return (
            f"REFUSED: custom skill {safe} already exists. "
            "Ask to overwrite if you want to replace it."
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    title = (name or safe).strip()
    desc = (description or title).strip()
    content = (
        f"---\nname: {title}\ndescription: {desc}\n---\n\n{(body or '').strip()}\n"
    )
    dest.write_text(content, encoding="utf-8")
    logger.info("SKILL: wrote custom skill %s", dest)
    return f"OK: saved custom skill {safe}"


def delete_custom_skill(slug: str) -> str:
    safe = _safe_slug(slug)
    dest = custom_skills_root() / safe / "SKILL.md"
    if not dest.is_file():
        return f"REFUSED: no custom skill named {safe}."
    dest.unlink()
    parent = dest.parent
    try:
        next(parent.iterdir())
    except StopIteration:
        parent.rmdir()
    except OSError:
        pass
    return f"OK: deleted custom skill {safe}"
