"""Spoken-output helpers: list summarization for TTS."""

from __future__ import annotations

import re

_LIST_ITEM_RE = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S+")
_NUMBERED_INLINE_RE = re.compile(
    r"(?:^|[.\n])\s*(?:\d+[.)]\s+[^\n]+)(?:\s*\d+[.)]\s+[^\n]+){3,}",
    re.M,
)


def summarize_for_speech(text: str, *, max_list_items: int = 3) -> str:
    """
    Keep chat text intact elsewhere; for TTS, collapse long enumerations.

    Example: a top-10 list becomes a short spoken summary instead of reading
    every entry aloud.
    """
    raw = (text or "").strip()
    if not raw:
        return raw

    lines = raw.splitlines()
    list_lines = [ln for ln in lines if _LIST_ITEM_RE.match(ln)]
    if len(list_lines) >= max_list_items + 1:
        prologue = []
        for ln in lines:
            if _LIST_ITEM_RE.match(ln):
                break
            if ln.strip():
                prologue.append(ln.strip())
        count = len(list_lines)
        lead = " ".join(prologue).strip()
        if lead:
            # Avoid duplicating an already-short summary.
            if len(lead.split()) <= 24 and count >= max_list_items:
                if not re.search(r"\b(here|list|top|following)\b", lead, re.I):
                    return f"{lead} Here are {count} items."
                return lead if lead.endswith((".", "!", "?")) else f"{lead}."
            return f"Here are {count} items."
        return f"Here are {count} items."

    if _NUMBERED_INLINE_RE.search(raw) and raw.count("\n") < 2:
        # Dense inline numbered list in one paragraph.
        return "Here is that list."

    # Very long spoken replies: keep first 2 sentences.
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    if len(sentences) >= 6 and len(raw) > 500:
        return " ".join(sentences[:2]).strip()
    return raw
