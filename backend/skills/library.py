"""Discover and load bundled Agent Skills (SKILL.md) for Marvin."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from backend.config import ROOT

logger = logging.getLogger(__name__)

# Obsidian format skills (kepano) — CLI / Defuddle remain Phase 2.
OBSIDIAN_SKILL_IDS = ("obsidian-markdown", "obsidian-bases", "json-canvas")
# Marvin feature skills (format/discipline, not executable plugins).
MARVIN_SKILL_IDS = ("daily-tasks", "web-search")
BUNDLED_SKILL_IDS = OBSIDIAN_SKILL_IDS + MARVIN_SKILL_IDS
# Backward-compatible alias used by older imports/tests.
FORMAT_SKILL_IDS = BUNDLED_SKILL_IDS
PHASE2_SKILL_IDS = ("obsidian-cli", "defuddle")

_DEFAULT_ENABLED = {
    "obsidian-markdown": True,
    "obsidian-bases": False,
    "json-canvas": False,
    "daily-tasks": True,
    "web-search": True,
}

_SKILL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("obsidian", OBSIDIAN_SKILL_IDS),
    ("marvin", MARVIN_SKILL_IDS),
)

_SKILLS_BASE = ROOT / "resources" / "skills"
_OBSIDIAN_ROOT = _SKILLS_BASE / "obsidian"
_MAX_SKILL_CHARS = 14_000

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z",
    re.DOTALL,
)


@dataclass(frozen=True)
class BundledSkill:
    skill_id: str
    name: str
    description: str
    body: str
    path: Path
    phase: int  # 1 = bundled, 2 = deferred
    group: str  # "obsidian" | "marvin" | "custom"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text.strip())
    if not match:
        return {}, text.strip()
    meta: dict[str, str] = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        if current_key and (line.startswith(" ") or line.startswith("\t")):
            meta[current_key] = f"{meta[current_key]} {line.strip()}".strip()
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().lstrip(">").strip().strip('"').strip("'")
        if not key:
            continue
        current_key = key
        meta[key] = value
    return meta, match.group(2).strip()


def skills_root() -> Path:
    """Primary skills directory (Obsidian formats); see also resources/skills/marvin."""
    return _OBSIDIAN_ROOT


def _load_skill(group: str, skill_id: str, base: Path) -> BundledSkill | None:
    skill_path = base / skill_id / "SKILL.md"
    if not skill_path.is_file():
        logger.warning("SKILL: missing bundled skill %s", skill_path)
        return None
    try:
        raw = skill_path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("SKILL: failed to read %s", skill_path)
        return None
    meta, body = _parse_frontmatter(raw)
    return BundledSkill(
        skill_id=skill_id,
        name=meta.get("name") or skill_id,
        description=meta.get("description") or "",
        body=body,
        path=skill_path,
        phase=1,
        group=group,
    )


def discover_bundled_skills(
    *,
    obsidian_root: Path | None = None,
    marvin_root: Path | None = None,
) -> list[BundledSkill]:
    """Discover all Phase-1 bundled skills across skill groups, plus custom."""
    roots = {
        "obsidian": obsidian_root or (_SKILLS_BASE / "obsidian"),
        "marvin": marvin_root or (_SKILLS_BASE / "marvin"),
    }
    found: list[BundledSkill] = []
    for group, skill_ids in _SKILL_GROUPS:
        base = roots[group]
        for skill_id in skill_ids:
            skill = _load_skill(group, skill_id, base)
            if skill is not None:
                found.append(skill)
    try:
        from backend.skills.custom import discover_custom_skills

        found.extend(discover_custom_skills())
    except Exception:
        logger.debug("SKILL: custom skills unavailable", exc_info=True)
    return found


def discover_format_skills(root: Path | None = None) -> list[BundledSkill]:
    """Backward-compatible alias for discover_bundled_skills."""
    if root is not None:
        # Legacy callers passed a single Obsidian root; still include Marvin skills.
        return discover_bundled_skills(obsidian_root=root)
    return discover_bundled_skills()


def load_skill_full_text(skill: BundledSkill, *, include_references: bool = True) -> str:
    """Load SKILL.md body plus optional references/, capped for prompt size."""
    parts = [f"# Skill: {skill.name}\n\n{skill.body}"]
    if include_references:
        refs_dir = skill.path.parent / "references"
        if refs_dir.is_dir():
            for ref in sorted(refs_dir.glob("*.md")):
                try:
                    ref_text = ref.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if ref_text:
                    parts.append(f"## Reference: {ref.name}\n\n{ref_text}")
    combined = "\n\n".join(parts).strip()
    if len(combined) > _MAX_SKILL_CHARS:
        combined = (
            combined[:_MAX_SKILL_CHARS].rstrip()
            + "\n\n[Skill truncated for prompt size.]"
        )
    return combined


def default_enabled_map() -> dict[str, bool]:
    return dict(_DEFAULT_ENABLED)


def catalog_block(skills: list[BundledSkill], enabled: dict[str, bool]) -> str:
    lines = [
        "Bundled skills available "
        "(follow skill guidance when writing notes, tasks, or using web search; "
        "vault I/O still uses Marvin tools):"
    ]
    for skill in skills:
        on = enabled.get(skill.skill_id, skill.group == "custom")
        status = "enabled" if on else "disabled"
        desc = skill.description or skill.name
        lines.append(f"- {skill.skill_id} [{status}]: {desc}")
    lines.append(
        "Phase 2 (not available): obsidian-cli, defuddle — require external CLIs."
    )
    return "\n".join(lines)


_TRIGGER_MARKERS: dict[str, tuple[str, ...]] = {
    "obsidian-markdown": (
        "wikilink",
        "callout",
        "frontmatter",
        "obsidian",
        "vault",
        "note",
        "daily note",
        "embed",
        "[[",
        "property",
        "properties",
        "markdown",
    ),
    "obsidian-bases": (
        "obsidian base",
        ".base",
        "bases view",
        "base file",
    ),
    "json-canvas": (
        "json canvas",
        ".canvas",
        "canvas file",
        "canvas node",
    ),
    "daily-tasks": (
        "task",
        "tasks",
        "todo",
        "to-do",
        "to do",
        "checklist",
        "check off",
        "mark complete",
        "incomplete",
        "daily plan",
        "plan my day",
        "agenda",
        "- [ ]",
    ),
    "web-search": (
        "search the web",
        "web search",
        "look up",
        "look it up",
        "google",
        "online",
        "on the internet",
        "current news",
        "latest news",
        "what's happening",
        "what is happening",
        "breaking news",
        "according to the web",
        "find online",
        "search online",
        "news about",
        "current events",
        "up to date",
        "up-to-date",
    ),
}


def skills_to_activate(
    *,
    routed_function: str,
    user_text: str,
    enabled: dict[str, bool],
    skills: list[BundledSkill] | None = None,
) -> list[BundledSkill]:
    """
    Strategy B: catalog is separate; return full bodies for relevant enabled skills.
    Always include obsidian-markdown on Obsidian-routed turns when enabled.
    Include daily-tasks on Obsidian / daily_planning turns or task triggers.
    """
    bundled = skills if skills is not None else discover_bundled_skills()
    lower = (user_text or "").lower()
    activate: list[BundledSkill] = []
    for skill in bundled:
        if not enabled.get(skill.skill_id, skill.group == "custom"):
            continue
        if routed_function == "obsidian" and skill.skill_id == "obsidian-markdown":
            activate.append(skill)
            continue
        if (
            routed_function in {"obsidian", "daily_planning"}
            and skill.skill_id == "daily-tasks"
        ):
            activate.append(skill)
            continue
        if routed_function == "web_search" and skill.skill_id == "web-search":
            activate.append(skill)
            continue
        if skill.group == "custom" and enabled.get(skill.skill_id, True):
            hay = f"{skill.skill_id} {skill.name} {skill.description}".lower()
            if routed_function in {"obsidian", "daily_planning"} or any(
                token and token in lower for token in hay.split() if len(token) > 3
            ):
                activate.append(skill)
                continue
        markers = _TRIGGER_MARKERS.get(skill.skill_id, ())
        if any(marker in lower for marker in markers):
            activate.append(skill)
    seen: set[str] = set()
    unique: list[BundledSkill] = []
    for skill in activate:
        if skill.skill_id in seen:
            continue
        seen.add(skill.skill_id)
        unique.append(skill)
    return unique


def build_skills_prompt_section(
    *,
    routed_function: str,
    user_text: str,
    enabled: dict[str, bool] | None = None,
) -> str:
    """Build catalog + selected full skill bodies for the system prompt."""
    from backend.skills.format_settings import load_format_skill_settings

    settings = enabled if enabled is not None else load_format_skill_settings()
    skills = discover_bundled_skills()
    if not skills:
        return ""

    parts = [catalog_block(skills, settings)]
    for skill in skills_to_activate(
        routed_function=routed_function,
        user_text=user_text,
        enabled=settings,
        skills=skills,
    ):
        parts.append(load_skill_full_text(skill))
    return "\n\n".join(parts).strip()
