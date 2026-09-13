"""Repeat detector and custom SKILL.md creator."""

from __future__ import annotations

from pathlib import Path

from backend.skills import custom as custom_skills
from backend.skills import library, repeats
from backend.skills.library import skills_to_activate


def test_normalize_intent_maps_homework_check_off():
    assert (
        repeats.normalize_intent("Use obsidian to check off precalc hw and bio hw")
        == "check_off|homework"
    )
    assert repeats.normalize_intent("check off tutoring") == "check_off|tutoring"


def test_normalize_intent_skips_reads_voice_lock_and_projects():
    assert repeats.normalize_intent("review my daily note") is None
    assert repeats.normalize_intent("summarize my tasks") is None
    assert repeats.normalize_intent("what's on my list") is None
    assert repeats.normalize_intent("enroll Voice Lock") is None
    assert repeats.normalize_intent("read Projects/Marvin") is None


def test_maybe_propose_skill_after_three_repeats(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repeats.clear_pending_skill_draft()
    phrase = "check off precalc hw"
    assert repeats.maybe_propose_skill(phrase) is None
    assert repeats.maybe_propose_skill(phrase) is None
    draft = repeats.maybe_propose_skill(phrase)
    assert draft is not None
    assert draft["slug"] == "check-off-homework"
    assert "complete_task" in draft["body"]
    assert repeats.maybe_propose_skill(phrase) is None


def test_save_custom_skill_requires_authorization_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    refused = custom_skills.save_custom_skill(
        "check-off-homework",
        "Check off homework",
        "Complete homework checkboxes.",
        "Call complete_task with authorized=true.",
        authorized=False,
    )
    assert refused.startswith("REFUSED:")
    ok = custom_skills.save_custom_skill(
        "check-off-homework",
        "Check off homework",
        "Complete homework checkboxes.",
        "Call complete_task with authorized=true.",
        authorized=True,
    )
    assert ok.startswith("OK:")
    exists = custom_skills.save_custom_skill(
        "check-off-homework",
        "Check off homework",
        "Complete homework checkboxes.",
        "replacement",
        authorized=True,
    )
    assert "already exists" in exists
    overwritten = custom_skills.save_custom_skill(
        "check-off-homework",
        "Check off homework",
        "Complete homework checkboxes.",
        "replacement",
        authorized=True,
        overwrite=True,
    )
    assert overwritten.startswith("OK:")
    found = custom_skills.discover_custom_skills()
    assert any(skill.skill_id == "check-off-homework" for skill in found)
    assert any(skill.group == "custom" for skill in found)
    assert custom_skills.delete_custom_skill("check-off-homework").startswith("OK:")


def test_try_save_pending_skill_on_authorise(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repeats.clear_pending_skill_draft()
    from backend.tools import obsidian as obsidian_tools

    obsidian_tools.clear_pending_write()
    phrase = "check off bio hw"
    assert repeats.maybe_propose_skill(phrase) is None
    assert repeats.maybe_propose_skill(phrase) is None
    assert repeats.maybe_propose_skill(phrase) is not None
    result = repeats.try_save_pending_skill("I authorise")
    assert result is not None and result.startswith("OK:")
    assert custom_skills.custom_skill_exists("check-off-homework")


def test_discover_bundled_includes_custom(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    custom_skills.save_custom_skill(
        "check-off-homework",
        "Check off homework",
        "Complete homework checkboxes.",
        "Call complete_task.",
        authorized=True,
    )
    ids = {skill.skill_id for skill in library.discover_bundled_skills()}
    assert "check-off-homework" in ids
    custom = next(
        skill
        for skill in library.discover_bundled_skills()
        if skill.skill_id == "check-off-homework"
    )
    active = skills_to_activate(
        routed_function="obsidian",
        user_text="check off homework",
        enabled={custom.skill_id: True},
        skills=[custom],
    )
    assert any(skill.skill_id == "check-off-homework" for skill in active)


def test_prompt_mentions_complete_task_authorization():
    from backend.config import SYSTEM_PROMPTS

    obsidian = SYSTEM_PROMPTS["obsidian"]
    assert "complete_task" in obsidian
    assert "authorized=true" in obsidian
    assert "check off" in obsidian
