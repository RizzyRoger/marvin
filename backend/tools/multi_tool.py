"""Compose multiple side-effect tool families for a single user turn."""

from __future__ import annotations

from typing import Any, Callable, Iterable

# Family id → tool-name matchers / tool schema providers are wired by the agent.
FAMILY_ORDER = (
    "spotify",
    "scrambler",
    "timers",
    "ai_model",
    "python_runner",
)

_FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
    "spotify": ("spotify",),
    "scrambler": ("scrambler_",),
    "timers": ("timer_",),
    "ai_model": ("switch_model",),
    "python_runner": ("run_python",),
}

_FAMILY_PROMPT: dict[str, str] = {
    "spotify": (
        "You MUST use a Spotify tool for the music request. "
        "Keep the spoken reply short; never invent track names. "
        "If a Spotify tool reports success, confirm that success."
    ),
    "scrambler": (
        "You MUST use a voice scrambler tool "
        "(scrambler_start, scrambler_stop, or scrambler_status). "
        "Scrambler sends anonymized mic audio to an output device for other apps."
    ),
    "timers": (
        "You MUST use a timer tool (timer_start, timer_cancel, timer_adjust, or "
        "timer_pause). Convert spoken durations to duration_seconds. "
        "If the user gave no timer name, omit name so it defaults to the duration label."
    ),
    "ai_model": (
        "You MUST use switch_model to change the AI model. "
        "Map spoken names: Claude/Anthropic→anthropic, Grok/xAI→xai, "
        "ChatGPT/GPT/OpenAI→openai, Qwen/local→local. "
        "Omit model_id unless the user named a specific catalog id."
    ),
    "python_runner": (
        "You MUST call run_python with authorized=true to execute the requested code. "
        "Summarize stdout briefly."
    ),
}


def family_for_tool_name(name: str) -> str | None:
    """Map a tool function name to its side-effect family id."""
    tool = name or ""
    for family, prefixes in _FAMILY_PREFIXES.items():
        for prefix in prefixes:
            if tool == prefix or tool.startswith(prefix):
                return family
    return None


def prefixes_for_families(families: Iterable[str]) -> list[str]:
    """Flatten matcher prefixes for required_tool_prefixes in chat_with_tools."""
    out: list[str] = []
    for family in families:
        out.extend(_FAMILY_PREFIXES.get(family, ()))
    return out


def primary_family(families: Iterable[str]) -> str:
    """Stable primary function id for message tagging."""
    wanted = set(families)
    for family in FAMILY_ORDER:
        if family in wanted:
            if family == "scrambler":
                return "voice_scrambler"
            return family
    return "chat"


def compose_prompt_blurb(families: Iterable[str]) -> str:
    """MUST-use instructions for each required family in this turn."""
    parts: list[str] = []
    ordered = [f for f in FAMILY_ORDER if f in set(families)]
    if len(ordered) > 1:
        parts.append(
            "This turn requires multiple tools. Call every required tool family "
            "before answering; do not skip any."
        )
    for family in ordered:
        blurb = _FAMILY_PROMPT.get(family)
        if blurb:
            parts.append(blurb)
    return " ".join(parts)


def compose_tools(
    families: Iterable[str],
    *,
    providers: dict[str, Callable[[], list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """Concatenate tool schemas for the requested families (stable order)."""
    tools: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        if family not in set(families):
            continue
        provider = providers.get(family)
        if provider is None:
            continue
        tools.extend(provider())
    return tools


def collect_required_families(
    *,
    spotify_required: bool,
    scrambler_needed: bool,
    timer_needed: bool,
    switch_needed: bool,
    python_needed: bool,
) -> list[str]:
    """Build ordered family list from decide_* flags."""
    families: list[str] = []
    if spotify_required:
        families.append("spotify")
    if scrambler_needed:
        families.append("scrambler")
    if timer_needed:
        families.append("timers")
    if switch_needed:
        families.append("ai_model")
    if python_needed:
        families.append("python_runner")
    return families


def tool_result_is_success(name: str, result: str) -> bool:
    """True when a side-effect tool appears to have completed successfully."""
    text = result or ""
    if text.startswith("Error:") or text.startswith("REFUSED:"):
        return False
    if text.startswith("Unknown tool:"):
        return False
    if "canceled" in text.lower() and text.startswith("REFUSED"):
        return False
    family = family_for_tool_name(name)
    if family is None:
        return False
    # Vault writes use OK: prefix; others return plain success sentences.
    if name in {
        "edit_note",
        "create_note",
        "create_daily_note",
        "delete_note",
        "complete_task",
        "save_custom_skill",
    }:
        return text.startswith("OK:")
    if family == "scrambler":
        lower = text.lower()
        return (
            "started" in lower
            or "stopped" in lower
            or "already running" in lower
            or "scrambler" in lower
        )
    return bool(text.strip())


def families_satisfied(
    required: Iterable[str],
    hit_families: Iterable[str],
) -> bool:
    needed = set(required)
    if not needed:
        return True
    return needed.issubset(set(hit_families))
