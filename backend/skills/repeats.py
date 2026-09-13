"""Count repeated user intents so Marvin can propose a custom skill."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path

from backend.skills.skill_file import _app_support_dir

logger = logging.getLogger(__name__)

THRESHOLD = 3
_COUNTS_NAME = "intent_counts.json"

_SKIP_RE = re.compile(
    r"\b("
    r"voice lock|enroll|review|summari[sz]e|what(?:'s| is) on|"
    r"list my|read my|check my note|projects?/"
    r")\b",
    re.I,
)
_VERB_RE = re.compile(
    r"\b("
    r"check(?:\s+it)?\s+off|check\s+off|"
    r"mark(?:\s+\w+)?\s+(?:as\s+)?(?:done|complete)|"
    r"create|edit|append|remind|timer|search the web|look up"
    r")\b",
    re.I,
)


def _counts_path() -> Path:
    return _app_support_dir() / "skills" / _COUNTS_NAME


def normalize_intent(user_message: str) -> str | None:
    """Return verb|object key, or None if this turn should not train a skill."""
    text = (user_message or "").strip()
    if not text or _SKIP_RE.search(text):
        return None
    if re.search(r"\bprojects?\b", text, re.I):
        return None
    verb_match = _VERB_RE.search(text)
    if not verb_match:
        return None
    verb = re.sub(r"\s+", "_", verb_match.group(1).lower())
    if "check" in verb and "off" in verb:
        verb = "check_off"
    rest = text[verb_match.end() :].lower()
    rest = re.sub(r"[^a-z0-9\s]+", " ", rest)
    tokens = [
        tok
        for tok in rest.split()
        if tok not in {"the", "a", "my", "to", "in", "on", "and", "use", "obsidian"}
    ]
    if any(tok in {"hw", "homework"} for tok in tokens):
        obj = "homework"
    elif tokens:
        obj = tokens[0]
    else:
        obj = "item"
    return f"{verb}|{obj}"


def record_intent(user_message: str) -> dict[str, int]:
    key = normalize_intent(user_message)
    if not key:
        return load_intent_counts()
    counts = load_intent_counts()
    counts[key] = int(counts.get(key, 0)) + 1
    _save_counts(counts)
    return counts


def load_intent_counts() -> dict[str, int]:
    path = _counts_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("SKILL: could not read intent counts")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if str(k) and int(v) >= 0}


def _save_counts(counts: dict[str, int]) -> None:
    path = _counts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(counts, indent=2, sort_keys=True) + "\n"
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix="intent-counts-", suffix=".json", dir=str(path.parent)
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


def draft_skill_from_intent(intent_key: str) -> dict[str, str]:
    verb, _, obj = intent_key.partition("|")
    label = obj.replace("_", " ") or "this request"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{verb}-{obj}").strip("-")[:40] or "custom"
    if verb == "check_off":
        body = (
            f"When the user asks to check off {label}, call complete_task "
            f"with authorized=true and a query naming each item.\n"
            "Join multiple items with 'and'.\n"
            "Prefer today's daily note unless they name another file.\n"
            "Do not invent completed tasks.\n"
            "If authorization is unclear, wait for I authorise."
        )
        name = f"Check off {label}"
        description = f"Complete {label} checkboxes in the daily note."
    else:
        body = (
            f"When the user repeats “{verb.replace('_', ' ')} {label}”, "
            "use the matching Marvin tool. Keep writes authorized only when they ask."
        )
        name = f"{verb.replace('_', ' ').title()} {label}"
        description = f"Repeated workflow: {verb.replace('_', ' ')} {label}."
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "body": body,
        "intent_key": intent_key,
    }


_PENDING_DRAFT: dict[str, str] | None = None


def pending_skill_draft() -> dict[str, str] | None:
    return _PENDING_DRAFT


def clear_pending_skill_draft() -> None:
    global _PENDING_DRAFT
    _PENDING_DRAFT = None


def maybe_propose_skill(user_message: str) -> dict[str, str] | None:
    """If this intent just reached the repeat threshold, return a draft."""
    global _PENDING_DRAFT
    from backend.skills.custom import custom_skill_exists

    key = normalize_intent(user_message)
    if not key:
        return None
    counts = record_intent(user_message)
    if int(counts.get(key, 0)) != THRESHOLD:
        return None
    draft = draft_skill_from_intent(key)
    if custom_skill_exists(draft["slug"]):
        return None
    _PENDING_DRAFT = draft
    return draft


def try_save_pending_skill(user_message: str) -> str | None:
    """Save the last proposed skill if this turn is consent."""
    from backend.tools.obsidian import (
        is_write_consent_only,
        pending_write_message,
    )
    from backend.skills.custom import save_custom_skill

    draft = pending_skill_draft()
    if not draft:
        return None
    lower = (user_message or "").lower()
    mentions_skill = bool(re.search(r"\bskill\b", lower))
    consent = is_write_consent_only(user_message)
    if not (mentions_skill or consent):
        return None
    if consent and not mentions_skill and pending_write_message():
        return None
    result = save_custom_skill(
        draft["slug"],
        draft["name"],
        draft["description"],
        draft["body"],
        authorized=True,
    )
    if result.startswith("OK:"):
        clear_pending_skill_draft()
    return result
