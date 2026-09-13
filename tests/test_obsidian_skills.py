"""Tests for bundled Agent Skills (Obsidian formats + Marvin feature skills)."""

from __future__ import annotations

from pathlib import Path

from backend.skills.library import (
    BUNDLED_SKILL_IDS,
    FORMAT_SKILL_IDS,
    MARVIN_SKILL_IDS,
    OBSIDIAN_SKILL_IDS,
    PHASE2_SKILL_IDS,
    build_skills_prompt_section,
    discover_bundled_skills,
    discover_format_skills,
    skills_to_activate,
)
from backend.skills.format_settings import (
    load_format_skill_settings,
    save_format_skill_settings,
)


def test_discover_bundled_skills_finds_obsidian_and_marvin():
    skills = discover_bundled_skills()
    ids = {s.skill_id for s in skills}
    assert set(BUNDLED_SKILL_IDS) <= ids
    assert set(FORMAT_SKILL_IDS) <= ids
    assert set(OBSIDIAN_SKILL_IDS) <= ids
    assert set(MARVIN_SKILL_IDS) <= ids
    assert "obsidian-cli" not in ids
    assert "defuddle" not in ids
    markdown = next(s for s in skills if s.skill_id == "obsidian-markdown")
    assert markdown.group == "obsidian"
    assert markdown.body
    daily = next(s for s in skills if s.skill_id == "daily-tasks")
    assert daily.group == "marvin"
    assert "[ ]" in daily.body or "checkbox" in daily.body.lower()
    web = next(s for s in skills if s.skill_id == "web-search")
    assert "web_search" in web.body or "[S1]" in web.body


def test_discover_format_skills_alias():
    assert {s.skill_id for s in discover_format_skills()} == {
        s.skill_id for s in discover_bundled_skills()
    }


def test_phase2_ids_documented_not_vendored():
    assert "obsidian-cli" in PHASE2_SKILL_IDS
    assert "defuddle" in PHASE2_SKILL_IDS
    root = Path(__file__).resolve().parents[1] / "resources" / "skills" / "obsidian"
    assert not (root / "obsidian-cli").exists()
    assert not (root / "defuddle").exists()
    assert (root / "NOTICE.md").is_file()
    marvin = Path(__file__).resolve().parents[1] / "resources" / "skills" / "marvin"
    assert (marvin / "NOTICE.md").is_file()
    assert (marvin / "daily-tasks" / "SKILL.md").is_file()
    assert (marvin / "web-search" / "SKILL.md").is_file()


def test_activate_markdown_on_obsidian_route():
    skills = discover_bundled_skills()
    enabled = {s.skill_id: False for s in skills}
    enabled["obsidian-markdown"] = True
    active = skills_to_activate(
        routed_function="obsidian",
        user_text="summarize my daily note",
        enabled=enabled,
        skills=skills,
    )
    assert [s.skill_id for s in active] == ["obsidian-markdown"]


def test_activate_daily_tasks_on_obsidian_route():
    skills = discover_bundled_skills()
    enabled = {s.skill_id: False for s in skills}
    enabled["daily-tasks"] = True
    active = skills_to_activate(
        routed_function="obsidian",
        user_text="plan my afternoon",
        enabled=enabled,
        skills=skills,
    )
    assert any(s.skill_id == "daily-tasks" for s in active)


def test_activate_daily_tasks_on_todo_trigger():
    skills = discover_bundled_skills()
    enabled = {s.skill_id: False for s in skills}
    enabled["daily-tasks"] = True
    active = skills_to_activate(
        routed_function="chat",
        user_text="add a todo to call the dentist",
        enabled=enabled,
        skills=skills,
    )
    assert any(s.skill_id == "daily-tasks" for s in active)


def test_activate_web_search_on_trigger():
    skills = discover_bundled_skills()
    enabled = {s.skill_id: False for s in skills}
    enabled["web-search"] = True
    active = skills_to_activate(
        routed_function="chat",
        user_text="look up the latest news about Mars",
        enabled=enabled,
        skills=skills,
    )
    assert any(s.skill_id == "web-search" for s in active)


def test_activate_web_search_on_web_search_route():
    skills = discover_bundled_skills()
    enabled = {s.skill_id: False for s in skills}
    enabled["web-search"] = True
    active = skills_to_activate(
        routed_function="web_search",
        user_text="who won yesterday",
        enabled=enabled,
        skills=skills,
    )
    assert any(s.skill_id == "web-search" for s in active)


def test_activate_canvas_on_trigger_when_enabled():
    skills = discover_bundled_skills()
    enabled = {s.skill_id: False for s in skills}
    enabled["json-canvas"] = True
    active = skills_to_activate(
        routed_function="chat",
        user_text="create a .canvas file for this project",
        enabled=enabled,
        skills=skills,
    )
    assert any(s.skill_id == "json-canvas" for s in active)


def test_build_prompt_includes_catalog_and_bodies(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    section = build_skills_prompt_section(
        routed_function="obsidian",
        user_text="read my daily note",
    )
    assert "obsidian-markdown" in section
    assert "daily-tasks" in section
    assert "Obsidian Flavored Markdown" in section or "wikilink" in section.lower()
    assert "Phase 2" in section


def test_format_skill_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    saved = save_format_skill_settings(
        {
            "obsidian-markdown": True,
            "obsidian-bases": True,
            "json-canvas": False,
            "daily-tasks": False,
            "web-search": True,
        }
    )
    assert saved["obsidian-bases"] is True
    assert saved["daily-tasks"] is False
    loaded = load_format_skill_settings()
    assert loaded["obsidian-bases"] is True
    assert loaded["json-canvas"] is False
    assert loaded["daily-tasks"] is False
    assert loaded["web-search"] is True
