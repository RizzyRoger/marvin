"""Strip leaked tool-call markup / faux invocations from assistant text."""

from __future__ import annotations

import re

# Known Marvin tool names that models sometimes dump into prose.
_TOOL_NAMES = (
    "find_incomplete_tasks",
    "complete_task",
    "edit_note",
    "create_daily_note",
    "create_note",
    "delete_note",
    "read_note",
    "read_best_note",
    "search_notes",
    "list_vault",
    "find_daily_note",
    "save_custom_skill",
    "web_search",
    "run_python",
    "switch_model",
    "scrambler_start",
    "scrambler_stop",
    "scrambler_status",
)

_TOOL_NAME_ALT = "|".join(_TOOL_NAMES)

_XML_TOOL_CALL_RE = re.compile(
    r"(?is)<\|?/?(?:tool_call|tool_calls?|function_call)\|?>|"
    r"</?(?:tool_call|tool_calls?|function_call)>"
)

_INLINE_JSON_TOOL_RE = re.compile(
    rf"(?is)\s*<?\s*{{\s*\"name\"\s*:\s*\"(?:{_TOOL_NAME_ALT})\".*?}}\s*"
)

# Avoid re.I here: it makes [a-z] match capitals and would eat "Checking".
_MON_GLUED_RE = re.compile(r"[Mm][Oo][Nn][a-z0-9]+(?=[A-Z])")
_MON_STANDALONE_RE = re.compile(r"\b[Mm][Oo][Nn][a-z0-9]+\b")
_TRAILING_TOOL_NAMES_RE = re.compile(
    rf"(?is)(?:\s+(?:{_TOOL_NAME_ALT}))+\s*$"
)
_ROUNDA_PREFIX_RE = re.compile(r"(?is)^(?:rounda|round)\s+")
_ROUNDA_SUFFIX_RE = re.compile(r"(?is)\s+(?:rounda|round)\s*$")
_BARE_TOOL_OR_ROUNDA_RE = re.compile(
    rf"(?is)^(?:(?:rounda|round)\s+)?(?:{_TOOL_NAME_ALT})$"
    r"|^(?:rounda|round)$"
)
_SPLIT = "<<<MARVIN_TOOL_LEAK>>>"


def scrub_tool_call_leakage(text: str) -> str:
    """Remove leaked tool-call markup while keeping the spoken answer."""
    cleaned = text or ""
    cleaned = _XML_TOOL_CALL_RE.sub(" ", cleaned)
    cleaned = _INLINE_JSON_TOOL_RE.sub(" ", cleaned)

    # Mark faux tool delimiters, then keep the last usable narrative chunk.
    cleaned = _MON_GLUED_RE.sub(_SPLIT, cleaned)
    cleaned = _MON_STANDALONE_RE.sub(_SPLIT, cleaned)
    parts = [p.strip() for p in cleaned.split(_SPLIT) if p and p.strip()]

    chosen = ""
    for part in reversed(parts):
        candidate = _ROUNDA_PREFIX_RE.sub("", part).strip()
        candidate = _TRAILING_TOOL_NAMES_RE.sub("", candidate).strip()
        candidate = _ROUNDA_SUFFIX_RE.sub("", candidate).strip()
        if not candidate or _BARE_TOOL_OR_ROUNDA_RE.match(candidate):
            continue
        chosen = candidate
        break

    cleaned = re.sub(r"[ \t]{2,}", " ", chosen)
    cleaned = re.sub(r" *\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
