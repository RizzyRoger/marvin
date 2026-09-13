"""Skill file package — user skill.md + bundled Agent Skills."""

from backend.skills.format_settings import (
    load_bundled_skill_settings,
    load_format_skill_settings,
    save_bundled_skill_settings,
    save_format_skill_settings,
)
from backend.skills.library import (
    BUNDLED_SKILL_IDS,
    FORMAT_SKILL_IDS,
    MARVIN_SKILL_IDS,
    OBSIDIAN_SKILL_IDS,
    PHASE2_SKILL_IDS,
    build_skills_prompt_section,
    discover_bundled_skills,
    discover_format_skills,
)
from backend.skills.skill_file import SkillFileService, get_skill_file_service

__all__ = [
    "BUNDLED_SKILL_IDS",
    "FORMAT_SKILL_IDS",
    "MARVIN_SKILL_IDS",
    "OBSIDIAN_SKILL_IDS",
    "PHASE2_SKILL_IDS",
    "SkillFileService",
    "build_skills_prompt_section",
    "discover_bundled_skills",
    "discover_format_skills",
    "get_skill_file_service",
    "load_bundled_skill_settings",
    "load_format_skill_settings",
    "save_bundled_skill_settings",
    "save_format_skill_settings",
]
