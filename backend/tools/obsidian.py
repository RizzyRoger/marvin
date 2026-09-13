"""Obsidian vault tools — read freely (except Projects), write only when authorized."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from backend.config import (
    OBSIDIAN_CACHE_TTL_SECONDS,
    OBSIDIAN_MAX_APPEND_CHARS,
    OBSIDIAN_BLOCKED_DIR_NAMES,
    OBSIDIAN_MAX_READ_CHARS,
    OBSIDIAN_MAX_WRITE_CHARS,
    VAULT_ROOT,
)

logger = logging.getLogger(__name__)

_HIDDEN = {".obsidian", ".trash", ".git", ".DS_Store"}
_QUERY_STOP_WORDS = {
    "a",
    "about",
    "at",
    "file",
    "find",
    "look",
    "my",
    "note",
    "notes",
    "open",
    "please",
    "read",
    "review",
    "the",
}
_NOTE_CACHE_LOCK = threading.Lock()
_NOTE_CACHE_AT = 0.0
_NOTE_CACHE_ROOT: Path | None = None
_NOTE_CACHE_PATHS: list[Path] = []
_CONTENT_CACHE: dict[Path, tuple[int, int, str]] = {}
_PENDING_WRITE_LOCK = threading.Lock()
_PENDING_WRITE_MESSAGE: str | None = None

_CONSENT_ONLY_RE = re.compile(
    r"^\s*("
    r"yes|yeah|yep|yup|ok|okay|sure|do it|go ahead|please|"
    r"i\s+authori[sz]e(?:\s+it)?|"
    r"you(?:'re| are) authorised|"
    r"you(?:'re| are) authorized|"
    r"use the (?:write|edit) tool"
    r")\s*[.!]?\s*$",
    re.I,
)
_AUTHORIZE_RE = re.compile(
    r"\b("
    r"i\s+authori[sz]e|"
    r"you(?:'re| are) authorised|"
    r"you(?:'re| are) authorized|"
    r"use the (?:write|edit) tool"
    r")\b",
    re.I,
)
_TASK_COMPLETE_RE = re.compile(
    r"\b("
    r"check(?:\s+it)?\s+off|"
    r"check\s+off|"
    r"mark(?:\s+\w[\w'-]*)?(?:\s+\w[\w'-]*){0,4}\s+(?:as\s+)?(?:done|complete|completed)|"
    r"mark\s+(?:this|that|the)\s+task|"
    r"complete\s+(?:the\s+)?task"
    r")\b",
    re.I,
)
_READ_CHECK_RE = re.compile(
    r"\bcheck\s+(?:my|the|this|that)\s+(?:note|notes|vault|file|document|journal)\b",
    re.I,
)


class VaultAccessError(PermissionError):
    """Raised when a path is blocked or unauthorized."""


def _relative(path: Path) -> Path:
    """Return a stable vault-relative path after resolving macOS aliases."""
    return path.resolve().relative_to(VAULT_ROOT.resolve())


def _resolve_safe(rel_path: str) -> Path:
    """Resolve a vault-relative path; raise if outside vault or under blocked dirs."""
    vault = VAULT_ROOT.resolve()
    raw = (rel_path or "").strip().lstrip("/")
    if not raw or raw in (".",):
        return vault

    candidate = (vault / raw).resolve()
    try:
        candidate.relative_to(vault)
    except ValueError as exc:
        raise VaultAccessError("Path escapes the vault") from exc

    rel = candidate.relative_to(vault)
    parts_lower = {p.lower() for p in rel.parts}
    blocked = {b.lower() for b in OBSIDIAN_BLOCKED_DIR_NAMES}
    if parts_lower & blocked:
        raise VaultAccessError(
            "Access to the Projects folder (and other blocked paths) is forbidden"
        )
    if any(p.startswith(".") and p not in (".", "..") for p in rel.parts):
        # Block hidden dirs like .obsidian
        if any(p in _HIDDEN or p.startswith(".") for p in rel.parts if p not in (".", "..")):
            raise VaultAccessError("Access to hidden vault folders is forbidden")
    return candidate


def is_write_consent_only(user_message: str) -> bool:
    """True for a short yes / authorise follow-up with no new request."""
    return bool(_CONSENT_ONLY_RE.match((user_message or "").strip()))


def pending_write_message() -> str | None:
    with _PENDING_WRITE_LOCK:
        return _PENDING_WRITE_MESSAGE


def clear_pending_write() -> None:
    global _PENDING_WRITE_MESSAGE
    with _PENDING_WRITE_LOCK:
        _PENDING_WRITE_MESSAGE = None


def remember_write_turn(user_message: str) -> None:
    """
    Keep a one-step pending write so 'I authorise' can complete the last check-off.
    Cleared on unrelated turns.
    """
    global _PENDING_WRITE_MESSAGE
    text = (user_message or "").strip()
    with _PENDING_WRITE_LOCK:
        if is_write_consent_only(text) and _PENDING_WRITE_MESSAGE:
            return
        if _message_grants_write(text):
            _PENDING_WRITE_MESSAGE = text
            return
        _PENDING_WRITE_MESSAGE = None


def effective_write_message(user_message: str) -> str:
    """Use the pending check-off text when this turn is only consent."""
    if is_write_consent_only(user_message):
        pending = pending_write_message()
        if pending:
            return pending
    return user_message or ""


def _message_grants_write(user_message: str) -> bool:
    """True when this message itself asks to change vault files."""
    lower = (user_message or "").lower()
    deny_patterns = [
        r"\b(do not|don't|dont|never)\s+(add|insert|put|edit|change|modify|write|delete|remove|create|mark|complete|check)",
        r"\b(without|no)\s+(adding|inserting|editing|changing|modifying|writing|deleting|removing)",
        r"\bread[- ]?only\b",
        r"\b(what|how)\b.*\b(would|should|could)\b.*\b(add|insert|put|edit|change|modify|delete|write)",
        r"\b(suggest|recommend)\b.*\b(add|edit|change|modification)",
        r"\bhow (?:do|can) (?:i|you)\b.*\b(add|insert|edit|change|delete|create)",
    ]
    if any(re.search(pattern, lower) for pattern in deny_patterns):
        return False
    if _READ_CHECK_RE.search(lower):
        return False
    if _AUTHORIZE_RE.search(lower):
        return True
    if _TASK_COMPLETE_RE.search(lower):
        return True

    vault_context = bool(
        re.search(
            r"\b("
            r"note|notes|vault|obsidian|daily|journal|file|document|"
            r"task|tasks|to-?dos?|checklist|markdown|\.md|"
            r"hw|homework"
            r")\b",
            lower,
        )
    )

    if re.search(
        r"\b(edit|update|change|rewrite|replace|append|add to|write to|modify)\b",
        lower,
    ):
        return True
    if re.search(r"\b(create|new note|delete|remove|erase)\b", lower):
        return True
    if re.search(r"\bmake\b", lower) and vault_context:
        return True
    if vault_context and re.search(
        r"\b(add|insert|put on|put in|put at|mark|complete|check off)\b",
        lower,
    ):
        return True
    if vault_context and re.search(r"\b(please )?(save|put that|apply)\b", lower):
        return True
    if re.search(r"\bsave (?:this |that |the )?skill\b", lower):
        return True
    return False


def user_grants_write(user_message: str) -> bool:
    """True when the user asked to change vault files, including a consent follow-up."""
    if _message_grants_write(user_message):
        return True
    return is_write_consent_only(user_message) and bool(pending_write_message())


def looks_like_deferred_write(reply: str) -> bool:
    """True when the model promises a vault edit instead of performing it."""
    lower = (reply or "").lower()
    return bool(
        re.search(
            r"\b("
            r"i'?ll (?:edit|add|update|write|append|change|modify|mark|complete|check)|"
            r"i will (?:edit|add|update|write|append|change|modify|mark|complete|check)|"
            r"let me (?:edit|add|update|write|append|change|mark|complete|check)|"
            r"i'?m going to (?:edit|add|update|write|append|change|mark|complete|check)|"
            r"i can (?:edit|add|update|write|append|change|mark|complete|check)|"
            r"i'?ll find .{0,80}\b(?:and )?(?:mark|complete|check)"
            r")\b",
            lower,
        )
    )


def looks_like_invented_write_claim(reply: str) -> bool:
    """True when the assistant claims a vault write completed without evidence."""
    lower = (reply or "").lower()
    return bool(
        re.search(
            r"\b("
            r"(?:i(?:'?ve| have)|we) (?:edited|updated|added|appended|rewrote|written|wrote|checked off)|"
            r"checked off|"
            r"marked .{0,60}\b(?:as )?(?:done|complete|completed)|"
            r"(?:note|file|vault) (?:has been|was) (?:edited|updated|changed|saved)|"
            r"done[.,]!?\s*(?:i )?(?:added|updated|edited|checked)"
            r")\b",
            lower,
        )
    )


def explicit_vault_intent(user_message: str) -> bool:
    """True for explicit vault / notes / task wording."""
    lower = (user_message or "").lower()
    phrases = (
        "obsidian",
        "vault",
        "daily note",
        "my note",
        "my notes",
        "my file",
        "check off",
        "check it off",
        "mark as done",
        "mark as complete",
        "mark complete",
        "mark done",
        "incomplete task",
        "to-do",
        "todo",
        "my tasks",
        "review my",
        "read my",
        "check my",
        "summarize my",
        "edit my",
        "create a note",
        "homework",
    )
    if any(phrase in lower for phrase in phrases):
        return True
    return bool(re.search(r"\b(hw|task|tasks|note|notes)\b", lower))


def _note_paths() -> list[Path]:
    """Return readable note paths, excluding hidden and blocked directories."""
    global _NOTE_CACHE_AT, _NOTE_CACHE_ROOT, _NOTE_CACHE_PATHS
    now = time.monotonic()
    vault = VAULT_ROOT.resolve()
    with _NOTE_CACHE_LOCK:
        if (
            _NOTE_CACHE_ROOT == vault
            and now - _NOTE_CACHE_AT < OBSIDIAN_CACHE_TTL_SECONDS
        ):
            return list(_NOTE_CACHE_PATHS)

    blocked = {b.lower() for b in OBSIDIAN_BLOCKED_DIR_NAMES}
    notes: list[Path] = []
    for path in vault.rglob("*.md"):
        try:
            rel = path.relative_to(vault)
        except ValueError:
            continue
        if any(part.lower() in blocked for part in rel.parts):
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        notes.append(path)
    with _NOTE_CACHE_LOCK:
        _NOTE_CACHE_AT = now
        _NOTE_CACHE_ROOT = vault
        _NOTE_CACHE_PATHS = notes
    return list(notes)


def _invalidate_note_cache() -> None:
    global _NOTE_CACHE_AT, _NOTE_CACHE_ROOT, _NOTE_CACHE_PATHS, _CONTENT_CACHE
    with _NOTE_CACHE_LOCK:
        _NOTE_CACHE_AT = 0.0
        _NOTE_CACHE_ROOT = None
        _NOTE_CACHE_PATHS = []
        _CONTENT_CACHE = {}


def _read_cached_note(path: Path) -> tuple[str, bool]:
    """Read note text once per file version; return (text, cache_hit)."""
    stat = path.stat()
    key = path.resolve()
    with _NOTE_CACHE_LOCK:
        cached = _CONTENT_CACHE.get(key)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2], True
    text = path.read_text(encoding="utf-8", errors="ignore")
    with _NOTE_CACHE_LOCK:
        _CONTENT_CACHE[key] = (stat.st_mtime_ns, stat.st_size, text)
    return text, False


def warm_note_cache() -> int:
    """Build the safe note-path index before the first vault request."""
    started = time.perf_counter()
    count = len(_note_paths())
    logger.info(
        "PERF: note_index_warm total=%.3fs notes=%d",
        time.perf_counter() - started,
        count,
    )
    return count


def _normal_words(value: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    useful = [word for word in words if word not in _QUERY_STOP_WORDS]
    return useful or words


def _note_match_score(query: str, path: Path) -> float:
    """Score how likely a vault path is to be the note implied by a query."""
    rel = _relative(path).as_posix()
    query_words = _normal_words(query)
    path_words = _normal_words(rel)
    query_text = " ".join(query_words)
    path_text = " ".join(path_words)
    stem_text = " ".join(_normal_words(path.stem))

    sequence = max(
        SequenceMatcher(None, query_text, stem_text).ratio(),
        SequenceMatcher(None, query_text, path_text).ratio(),
    )
    overlap = len(set(query_words) & set(path_words)) / max(len(set(query_words)), 1)
    score = sequence * 0.55 + overlap * 0.45

    lower_query = query.lower()
    lower_rel = rel.lower()
    if query_text and query_text in path_text:
        score += 0.35
    if path.stem.lower() in lower_query:
        score += 0.25
    if "daily" in lower_query and "daily" in lower_rel:
        score += 0.5
        if date.today().isoformat() in path.name:
            score += 0.75
    return score


def resolve_note(query: str, max_results: int = 5) -> list[tuple[Path, float]]:
    """Resolve an imprecise description to ranked vault note candidates."""
    query = (query or "").strip()
    if not query:
        return []
    ranked = [
        (path, _note_match_score(query, path))
        for path in _note_paths()
    ]
    ranked.sort(key=lambda item: (-item[1], item[0].as_posix().lower()))
    return ranked[:max_results]


def find_note(query: str, max_results: int = 5) -> str:
    """Find notes from an approximate name or natural-language description."""
    matches = resolve_note(query, max_results=max_results)
    if not matches:
        return f"No note candidates found for '{query}'."
    lines = [
        f"- {_relative(path).as_posix()} (confidence {min(score, 1.0):.2f})"
        for path, score in matches
    ]
    return (
        f"Likely notes for '{query}', best match first:\n"
        + "\n".join(lines)
    )


def read_best_note(query: str) -> str:
    """Infer the note meant by a description and read the best candidate."""
    matches = resolve_note(query, max_results=3)
    if not matches:
        return f"No note candidates found for '{query}'."
    best_path, best_score = matches[0]
    rel = _relative(best_path).as_posix()
    alternatives = ", ".join(
        _relative(path).as_posix()
        for path, _score in matches[1:]
    )
    context = (
        f"Inferred '{query}' as '{rel}' "
        f"(confidence {min(best_score, 1.0):.2f})."
    )
    if alternatives:
        context += f" Other candidates: {alternatives}."
    return context + "\n\n" + read_note(rel)


def _atomic_write(target: Path, content: str) -> None:
    """Atomically replace a note so interrupted writes cannot corrupt it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = target.stat().st_mode if target.exists() else None
    fd, temp_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=".marvin-",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if existing_mode is not None:
            os.chmod(temp_path, existing_mode)
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def list_vault(path: str = "", max_entries: int = 80) -> str:
    """List files and folders under a vault path (Projects excluded)."""
    root = _resolve_safe(path)
    if not root.exists():
        return f"Path not found: {path or '/'}"
    if root.is_file():
        return f"File: {_relative(root)}"

    entries: list[str] = []
    blocked = {b.lower() for b in OBSIDIAN_BLOCKED_DIR_NAMES}
    try:
        children = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        return f"Could not list directory: {exc}"

    for child in children:
        name = child.name
        if name in _HIDDEN or name.startswith("."):
            continue
        if name.lower() in blocked:
            continue
        rel = _relative(child).as_posix()
        if child.is_dir():
            entries.append(f"[dir]  {rel}/")
        elif child.suffix.lower() in {".md", ".txt", ".canvas"}:
            entries.append(f"[note] {rel}")
        else:
            entries.append(f"[file] {rel}")
        if len(entries) >= max_entries:
            entries.append("… truncated")
            break

    header = f"Vault listing for '{path or '/'}' ({len(entries)} items):"
    return header + "\n" + "\n".join(entries) if entries else header + "\n(empty)"


def find_daily_note(day: str | None = None) -> str:
    """Locate today's (or a given YYYY-MM-DD) daily note under daily notes/."""
    if day:
        try:
            target = date.fromisoformat(day)
        except ValueError:
            return f"Invalid date '{day}'. Use YYYY-MM-DD."
    else:
        target = date.today()

    daily_root = _resolve_safe("daily notes")
    if not daily_root.exists():
        return "No 'daily notes' folder found."

    # Common Obsidian daily note patterns
    candidates = [
        f"{target.isoformat()}.md",
        f"{target.strftime('%Y-%m-%d')}.md",
        f"{target.strftime('%Y%m%d')}.md",
        f"{target.strftime('%B %-d, %Y')}.md",
        f"{target.strftime('%b %-d, %Y')}.md",
    ]
    # Also scan for files containing the ISO date
    matches: list[Path] = []
    for p in daily_root.rglob("*.md"):
        if "projects" in {part.lower() for part in _relative(p).parts}:
            continue
        name = p.name
        if name in candidates or target.isoformat() in name:
            matches.append(p)

    if not matches:
        # Return listing of recent daily notes to help
        recent = sorted(daily_root.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:8]
        names = [_relative(r).as_posix() for r in recent]
        return (
            f"No daily note found for {target.isoformat()}. "
            f"Recent daily notes: {', '.join(names) if names else '(none)'}"
        )

    # Prefer exact ISO filename
    matches.sort(key=lambda p: (0 if p.name.startswith(target.isoformat()) else 1, p.name))
    best = matches[0]
    return f"Found: {_relative(best).as_posix()}"


def read_note(path: str, max_chars: int | None = None) -> str:
    """Read a markdown/text note from the vault."""
    target = _resolve_safe(path)
    inferred_from = ""
    if not target.exists():
        matches = resolve_note(path, max_results=1)
        if not matches:
            return f"Note not found: {path}"
        target, score = matches[0]
        inferred_from = (
            f"Inferred '{path}' as '{_relative(target).as_posix()}' "
            f"(confidence {min(score, 1.0):.2f}).\n\n"
        )
    if target.is_dir():
        return list_vault(path)
    if target.suffix.lower() not in {".md", ".txt", ".canvas", ""}:
        return f"Refusing to read non-text file: {path}"

    limit = max_chars or OBSIDIAN_MAX_READ_CHARS
    try:
        text, cache_hit = _read_cached_note(target)
    except OSError as exc:
        return f"Could not read note: {exc}"
    logger.info("PERF: read_note cache_hit=%s path=%s", cache_hit, target.name)

    rel = _relative(target).as_posix()
    if len(text) > limit:
        return (
            f"{inferred_from}# {rel}\n\n{text[:limit]}"
            f"\n\n… truncated ({len(text)} chars total)"
        )
    return f"{inferred_from}# {rel}\n\n{text}"


def search_notes(query: str, max_results: int = 12) -> str:
    """Rank title/content matches while caching unchanged note contents."""
    started = time.perf_counter()
    q = (query or "").strip().lower()
    if not q:
        return "Empty search query."

    query_words = _normal_words(q)
    ranked: list[tuple[float, str]] = []
    cache_hits = 0
    files_read = 0

    for path in _note_paths():
        rel = _relative(path).as_posix()
        name = path.stem.lower()
        try:
            body, cache_hit = _read_cached_note(path)
        except OSError:
            continue
        cache_hits += int(cache_hit)
        files_read += int(not cache_hit)
        body_lower = body.lower()
        title_matches = sum(word in name for word in query_words)
        content_matches = sum(word in body_lower for word in query_words)
        exact_title = q in name
        exact_content = q in body_lower
        if not (title_matches or content_matches or exact_title or exact_content):
            continue

        score = (
            title_matches * 4
            + content_matches
            + int(exact_title) * 8
            + int(exact_content) * 3
            + _note_match_score(query, path) * 5
        )
        first_term = next(
            (term for term in query_words if term in body_lower),
            q,
        )
        idx = body_lower.find(first_term)
        snippet = ""
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(body), idx + len(first_term) + 60)
            snippet = body[start:end].replace("\n", " ")
        ranked.append((score, f"- {rel} … {snippet}"))

    ranked.sort(key=lambda item: (-item[0], item[1].lower()))
    hits = [line for _score, line in ranked[:max_results]]
    logger.info(
        "PERF: search_notes total=%.3fs files_read=%d cache_hits=%d results=%d",
        time.perf_counter() - started,
        files_read,
        cache_hits,
        len(hits),
    )
    if not hits:
        return f"No notes matching '{query}'."
    return f"Search results for '{query}':\n" + "\n".join(hits)


def edit_note(
    path: str,
    new_content: str,
    mode: str = "replace",
    authorized: bool = False,
    user_authorized: bool = False,
) -> str:
    """
    Edit a note. Requires both model authorized=True and user_authorized
    (user message explicitly requested a change). Caps write size.
    """
    if not authorized or not user_authorized:
        return (
            "REFUSED: edits require explicit user authorization. "
            "Ask the user to clearly say they want the note edited, then call again "
            "with authorized=true."
        )

    content = new_content or ""
    if len(content) > OBSIDIAN_MAX_WRITE_CHARS:
        return (
            f"REFUSED: content too large ({len(content)} chars). "
            f"Max is {OBSIDIAN_MAX_WRITE_CHARS}. Split into smaller edits."
        )

    target = _resolve_safe(path)
    if not target.exists():
        return (
            "REFUSED: edit_note cannot create a missing note. "
            "Use create_note only when the user explicitly asked to create it."
        )
    if target.exists() and target.is_dir():
        return f"REFUSED: path is a directory: {path}"

    mode = (mode or "replace").lower()
    if mode not in {"replace", "append"}:
        return "REFUSED: mode must be 'replace' or 'append'"

    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and target.exists():
        existing = target.read_text(encoding="utf-8")
        if len(content) > OBSIDIAN_MAX_APPEND_CHARS:
            return (
                f"REFUSED: append content is too large ({len(content)} chars). "
                f"Max append size is {OBSIDIAN_MAX_APPEND_CHARS}."
            )
        if content.strip() and (
            content.strip() in existing
            or SequenceMatcher(None, existing, content).ratio() > 0.6
        ):
            return (
                "REFUSED: append content substantially duplicates the existing note."
            )
        if not existing.endswith("\n") and content and not content.startswith("\n"):
            content = "\n" + content
        _atomic_write(target, existing + content)
    else:
        _atomic_write(target, content)

    rel = _relative(target).as_posix()
    _invalidate_note_cache()
    logger.info("Edited note %s mode=%s chars=%d", rel, mode, len(content))
    return f"OK: wrote {len(content)} chars to {rel} ({mode})"


def create_note(
    path: str,
    content: str = "",
    authorized: bool = False,
    user_authorized: bool = False,
) -> str:
    if not authorized or not user_authorized:
        return (
            "REFUSED: creating notes requires explicit user authorization "
            "(authorized=true after the user asks to create)."
        )
    if len(content or "") > OBSIDIAN_MAX_WRITE_CHARS:
        return f"REFUSED: content too large. Max {OBSIDIAN_MAX_WRITE_CHARS} chars."

    target = _resolve_safe(path)
    if not path.lower().endswith(".md"):
        target = _resolve_safe(path + ".md")
    if target.exists():
        return f"REFUSED: note already exists: {_relative(target).as_posix()}"

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(content or "")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return f"REFUSED: note already exists: {_relative(target).as_posix()}"
    rel = _relative(target).as_posix()
    _invalidate_note_cache()
    return f"OK: created {rel}"


def create_daily_note(
    day: str = "today",
    content: str = "",
    authorized: bool = False,
    user_authorized: bool = False,
) -> str:
    """Create a daily note using a server-resolved date and canonical folder."""
    normalized = (day or "today").strip().lower()
    if normalized == "today":
        target_day = date.today()
    elif normalized == "tomorrow":
        target_day = date.today() + timedelta(days=1)
    else:
        try:
            target_day = date.fromisoformat(normalized)
        except ValueError:
            return "REFUSED: daily-note day must be today, tomorrow, or YYYY-MM-DD."

    body = content if content.strip() else f"# {target_day.isoformat()}\n"
    return create_note(
        path=f"daily notes/{target_day.isoformat()}.md",
        content=body,
        authorized=authorized,
        user_authorized=user_authorized,
    )


def handle_direct_daily_note_create(user_message: str) -> str | None:
    """Handle an unadorned today/tomorrow daily-note request deterministically."""
    lower = (user_message or "").lower()
    is_create = bool(re.search(r"\b(create|make|new)\b", lower))
    is_daily_target = "daily note" in lower or bool(
        re.search(r"\bnote\s+(?:for\s+)?(?:today|tomorrow)\b", lower)
    )
    asks_for_content = bool(
        re.search(r"\b(with|containing|include|saying|that says|add)\b", lower)
        or ":" in user_message
    )
    if not (is_create and is_daily_target) or asks_for_content:
        return None

    day = "tomorrow" if "tomorrow" in lower else "today"
    result = create_daily_note(
        day=day,
        authorized=True,
        user_authorized=user_grants_write(user_message),
    )
    if result.startswith("OK: "):
        return result[4:].capitalize() + "."
    return result


def resolve_daily_note(day: str | None = None) -> dict[str, str]:
    """Locate a daily note; tests and complete_task share this helper."""
    located = find_daily_note(day)
    if located.startswith("Found:"):
        rel = located.split("Found:", 1)[1].strip()
        iso = day if day and re.match(r"^\d{4}-\d{2}-\d{2}$", day) else date.today().isoformat()
        return {"status": "found", "path": rel, "date": iso}
    return {"status": "missing", "message": located}


def _resolve_daily_note_path(day: str | None = None) -> Path | None:
    located = resolve_daily_note(day)
    if located.get("status") != "found":
        return None
    try:
        return _resolve_safe(located["path"])
    except VaultAccessError:
        return None


def _extract_task_query(user_message: str) -> str:
    """Strip check-off / authorise phrasing so complete_task gets the task names."""
    text = (user_message or "").strip()
    text = re.sub(r"^(?:please\s+)?(?:use\s+obsidian\s+to\s+)", "", text, flags=re.I)
    text = re.sub(r"^(?:please\s+)", "", text, flags=re.I)
    text = re.sub(
        r"^(?:"
        r"check(?:\s+it)?\s+off|"
        r"mark(?:\s+\w[\w'-]*)?(?:\s+\w[\w'-]*){0,4}\s+(?:as\s+)?(?:done|complete|completed)|"
        r"complete\s+(?:the\s+)?task"
        r")\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s*\b(?:i\s+authori[sz]e|you(?:'re| are) authori[sz]ed|use the (?:write|edit) tool)\b.*$",
        "",
        text,
        flags=re.I,
    )
    return text.strip(" .!")


def _parse_incomplete_tasks(
    text: str,
    *,
    source_path: str,
    context_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract incomplete Markdown / TODO-style tasks from note text."""
    tasks: list[dict[str, Any]] = []
    heading = ""
    terms = [term.lower() for term in (context_terms or []) if term.strip()]
    completed = re.compile(r"^\s*[-*+]\s+\[(?:x|X|✔|✓)\]\s+")
    unchecked = re.compile(
        r"^\s*[-*+]\s+\[(?: |/|todo|TODO|next|Next)\]\s+(?P<body>.+?)\s*$"
    )
    todo_line = re.compile(
        r"^\s*(?:[-*+]\s+)?(?:TODO|To[- ]?do|NEXT|Action item)\s*[:.-]\s*(?P<body>.+?)\s*$",
        re.I,
    )
    for line in text.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            heading = heading_match.group(2).strip()
            continue
        if completed.match(line):
            continue
        body = None
        kind = "checkbox"
        match = unchecked.match(line)
        if match:
            body = match.group("body").strip()
        else:
            match = todo_line.match(line)
            if match:
                body = match.group("body").strip()
                kind = "todo"
        if not body:
            continue
        context_hit = False
        if terms:
            context_hit = any(
                term in body.lower() or term in heading.lower() for term in terms
            )
        tasks.append(
            {
                "text": body,
                "heading": heading,
                "path": source_path,
                "kind": kind,
                "context_match": context_hit,
                "line": line.strip(),
            }
        )
    return tasks


def _normalize_context_terms(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    terms = [text]
    lower = text.lower()
    if lower not in {t.lower() for t in terms}:
        terms.append(lower)
    compact = re.sub(r"[-\s]+", "", lower)
    if compact and compact not in {t.lower() for t in terms}:
        terms.append(compact)
    return terms


def find_incomplete_tasks(day: str | None = None, context: str = "") -> str:
    """Retrieve incomplete tasks, preferring today's daily note."""
    terms = _normalize_context_terms(context)
    collected: list[dict[str, Any]] = []
    notes_checked: list[str] = []

    def ingest(path: Path) -> None:
        rel = _relative(path).as_posix()
        if rel in notes_checked:
            return
        notes_checked.append(rel)
        try:
            text, _ = _read_cached_note(path)
        except OSError:
            return
        collected.extend(
            _parse_incomplete_tasks(text, source_path=rel, context_terms=terms)
        )

    daily = _resolve_daily_note_path(day)
    if daily is not None:
        ingest(daily)
    if terms and not any(t.get("context_match") for t in collected):
        for path in _note_paths():
            if _relative(path).as_posix() in notes_checked:
                continue
            try:
                body, _ = _read_cached_note(path)
            except OSError:
                continue
            if any(term.lower() in body.lower() for term in terms):
                ingest(path)
            if len(notes_checked) > 40:
                break

    incomplete = collected
    if terms:
        prioritized = [task for task in incomplete if task.get("context_match")]
        if prioritized:
            incomplete = prioritized + [
                task for task in incomplete if not task.get("context_match")
            ]
    if not incomplete:
        return (
            "STATUS=success_empty "
            f"notes_checked={notes_checked} "
            "Search completed successfully and found no incomplete tasks."
        )
    lines = [f"STATUS=success incomplete_count={len(incomplete)}"]
    for task in incomplete[:80]:
        origin = f" [{task['path']}]"
        lines.append(f"- [ ] {task['text']}{origin}")
    return "\n".join(lines)


def _score_task_match(query: str, task_text: str) -> float:
    q = (query or "").strip().lower()
    body = (task_text or "").strip().lower()
    if not q or not body:
        return 0.0
    if q == body:
        return 1.0
    if q in body or body in q:
        return 0.92
    q_tokens = {t for t in re.split(r"[^\w]+", q) if len(t) >= 2}
    b_tokens = {t for t in re.split(r"[^\w]+", body) if len(t) >= 2}
    if not q_tokens or not b_tokens:
        return SequenceMatcher(None, q, body).ratio()
    overlap = len(q_tokens & b_tokens) / max(len(q_tokens), 1)
    fuzzy = SequenceMatcher(None, q, body).ratio()
    return max(overlap, fuzzy * 0.85)


def _complete_checkbox_line(line: str) -> str | None:
    unchecked = re.compile(
        r"^(\s*[-*+]\s+)\[(?: |/|todo|TODO|next|Next)\](\s+.*)$"
    )
    match = unchecked.match(line)
    if match:
        return f"{match.group(1)}[x]{match.group(2)}"
    todo_line = re.compile(
        r"^(\s*(?:[-*+]\s+)?)(?:TODO|To[- ]?do|NEXT|Action item)(\s*[:.-]\s*.+)$",
        re.I,
    )
    match = todo_line.match(line)
    if match:
        return f"{match.group(1)}- [x]{match.group(2)}"
    return None


def _complete_one_task(
    query: str,
    *,
    path: str = "",
    day: str | None = None,
    authorized: bool = False,
    user_authorized: bool = False,
) -> str:
    if not authorized or not user_authorized:
        return (
            "REFUSED: completing a task requires explicit user authorization. "
            "Ask the user to clearly request the check-off, then call again "
            "with authorized=true."
        )
    q = (query or "").strip()
    if not q:
        return "REFUSED: complete_task requires a non-empty query describing the task."

    if path:
        target = _resolve_safe(path)
        if not target.exists() or not target.is_file():
            return f"REFUSED: note not found: {path}"
        rel = _relative(target).as_posix()
    else:
        target = _resolve_daily_note_path(day)
        if target is None:
            return "REFUSED: no daily note found for that day."
        rel = _relative(target).as_posix()

    text = target.read_text(encoding="utf-8")
    tasks = _parse_incomplete_tasks(
        text, source_path=rel, context_terms=_normalize_context_terms(q)
    )
    if not tasks:
        return f"REFUSED: no incomplete tasks found in {rel}."

    ranked = sorted(
        ((_score_task_match(q, t["text"]), t) for t in tasks),
        key=lambda row: (-row[0], row[1]["text"].lower()),
    )
    best_score, best = ranked[0]
    if best_score < 0.35:
        sample = ", ".join(t["text"] for _s, t in ranked[:3])
        return (
            f"REFUSED: no incomplete task closely matched {q!r} in {rel}. "
            f"Nearby: {sample}."
        )

    lines = text.splitlines(keepends=True)
    target_stripped = best["line"]
    replaced = False
    new_lines: list[str] = []
    for raw in lines:
        stripped = raw.rstrip("\n\r")
        if not replaced and stripped.strip() == target_stripped:
            completed = _complete_checkbox_line(stripped)
            if completed is None:
                return (
                    f"REFUSED: matched task is not a toggleable checkbox/TODO line "
                    f"in {rel}: {target_stripped}"
                )
            ending = raw[len(stripped) :]
            new_lines.append(completed + ending)
            replaced = True
        else:
            new_lines.append(raw)
    if not replaced:
        return f"REFUSED: could not locate task line in {rel}: {target_stripped}"

    _atomic_write(target, "".join(new_lines))
    _invalidate_note_cache()
    logger.info("Completed task in %s query=%r text=%r", rel, q, best["text"])
    return f"OK: checked off “{best['text']}” in {rel}"


def complete_task(
    query: str,
    path: str = "",
    day: str | None = None,
    *,
    authorized: bool = False,
    user_authorized: bool = False,
) -> str:
    """
    Check off the best-matching incomplete task. If the query lists several
    items joined by 'and', complete each match that scores well.
    """
    q = (query or "").strip()
    parts = [part.strip() for part in re.split(r"\s+and\s+", q, flags=re.I) if part.strip()]
    if len(parts) <= 1:
        return _complete_one_task(
            q,
            path=path,
            day=day,
            authorized=authorized,
            user_authorized=user_authorized,
        )
    results = [
        _complete_one_task(
            part,
            path=path,
            day=day,
            authorized=authorized,
            user_authorized=user_authorized,
        )
        for part in parts
    ]
    oks = [row for row in results if row.startswith("OK:")]
    if oks and len(oks) == len(results):
        return " ".join(oks)
    if oks:
        return " ".join(results)
    return results[0]


def delete_note(
    path: str,
    authorized: bool = False,
    user_authorized: bool = False,
) -> str:
    if not authorized or not user_authorized:
        return (
            "REFUSED: deletion requires explicit user authorization "
            "(user must say delete/remove, and authorized=true)."
        )
    # Extra hard gate: user must mention delete/remove in their message
    # (caller sets user_authorized only when those words appear for deletes)

    target = _resolve_safe(path)
    if not target.exists():
        return f"Note not found: {path}"
    if target.is_dir():
        return "REFUSED: will not delete directories"
    target.unlink()
    _invalidate_note_cache()
    return f"OK: deleted {_relative(target).as_posix()}"


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_vault",
            "description": "List folders and notes in the Obsidian vault. Projects is always hidden/blocked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative folder path. Empty string = vault root.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_note",
            "description": (
                "Find likely notes from an approximate filename or natural-language "
                "description. Use when the user does not give an exact path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What the user called or implied the file was",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_best_note",
            "description": (
                "Infer which note the user means and read it in one call. Prefer this "
                "for requests such as 'review my daily note' or approximate names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's description of the intended note",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_daily_note",
            "description": "Find the daily note for today or a given date (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Optional date YYYY-MM-DD. Defaults to today.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_incomplete_tasks",
            "description": (
                "Find incomplete tasks (unchecked checkboxes, TODO/NEXT lines) preferably "
                "from today's daily note. Optional context narrows matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Optional date YYYY-MM-DD. Defaults to today.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional term such as precalc or bio",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": (
                "Check off one or more incomplete tasks by flipping [ ] to [x] "
                "in today's daily note or a given path. Use for 'check off …' / "
                "'mark … done'. Set authorized=true when the user asked. "
                "Prefer this over edit_note for checkbox completion. "
                "You may pass several items joined by 'and'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Task description, e.g. 'precalc hw and bio hw'",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional vault-relative note path. Empty = today's daily note.",
                    },
                    "day": {
                        "type": "string",
                        "description": "Optional date YYYY-MM-DD when using the daily note.",
                    },
                    "authorized": {
                        "type": "boolean",
                        "description": "Must be true when the user asked to check the task off.",
                    },
                },
                "required": ["query", "authorized"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": (
                "Read a vault note. Exact paths are preferred, but an approximate "
                "name is resolved automatically. Never use for Projects paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative note path, e.g. 'daily notes/2026-07-15.md'",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Search note titles and contents for a query string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_note",
            "description": (
                "Replace or append note content. ONLY when the user explicitly asked to edit. "
                "Set authorized=true only then. Never touch Projects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "new_content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["replace", "append"]},
                    "authorized": {
                        "type": "boolean",
                        "description": "Must be true only if user explicitly asked to edit",
                    },
                },
                "required": ["path", "new_content", "authorized"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_daily_note",
            "description": (
                "Create a daily note in the canonical 'daily notes' folder. "
                "Use for today/tomorrow instead of calculating a date or path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": ["today", "tomorrow"],
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Only content explicitly requested in the current message. "
                            "Leave empty for a blank dated note."
                        ),
                    },
                    "authorized": {"type": "boolean"},
                },
                "required": ["day", "authorized"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Create a new .md note. Requires explicit user request and authorized=true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "authorized": {"type": "boolean"},
                },
                "required": ["path", "authorized"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Delete a note. Requires explicit delete/remove request and authorized=true. Never delete folders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "authorized": {"type": "boolean"},
                },
                "required": ["path", "authorized"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_custom_skill",
            "description": (
                "Save a custom SKILL.md after the user said yes / authorise / save this skill. "
                "Never overwrite an existing slug unless overwrite=true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "body": {
                        "type": "string",
                        "description": "5–10 lines of how-to for this repeated workflow.",
                    },
                    "overwrite": {"type": "boolean"},
                    "authorized": {"type": "boolean"},
                },
                "required": ["slug", "name", "description", "body", "authorized"],
            },
        },
    },
]


def prefetch_read_request(user_message: str) -> str | None:
    """Resolve common read-only vault requests before invoking the LLM."""
    if user_grants_write(user_message):
        return None
    lower = (user_message or "").lower()
    if re.search(r"\bprojects?\b", lower):
        return "REFUSED: access to the Projects folder is forbidden."
    if re.search(r"\b(list|show)\b.*\b(vault|folders?|files?|notes?)\b", lower):
        return list_vault()
    if re.search(r"\bsearch\b.*\b(notes?|vault)\b", lower):
        query = lower.split(" for ", 1)[-1] if " for " in lower else user_message
        return search_notes(query)
    if re.search(
        r"\b(left to do|incomplete task|open task|to-?dos?|what.*(task|to do))\b",
        lower,
    ):
        return find_incomplete_tasks()
    if re.search(
        r"\b(read|review|summari[sz]e|open|find|look through)\b",
        lower,
    ) or "daily note" in lower:
        return read_best_note(user_message)
    if _READ_CHECK_RE.search(lower):
        return read_best_note(user_message)
    return None


def tools_for_request(user_message: str) -> list[dict]:
    """Send only relevant schemas to Qwen to reduce prompt processing."""
    lower = (user_message or "").lower()
    by_name = {
        tool["function"]["name"]: tool
        for tool in TOOL_DEFINITIONS
    }
    if re.search(r"\b(delete|remove|erase)\b", lower):
        names = ("find_note", "delete_note")
    elif re.search(r"\b(create|make|new note)\b", lower) and not _TASK_COMPLETE_RE.search(lower):
        if "daily note" in lower or re.search(
            r"\bnote\s+(?:for\s+)?(?:today|tomorrow)\b",
            lower,
        ):
            names = ("create_daily_note",)
        else:
            names = ("create_note",)
    elif user_grants_write(user_message):
        if _TASK_COMPLETE_RE.search(effective_write_message(user_message)):
            names = (
                "complete_task",
                "find_incomplete_tasks",
                "find_daily_note",
                "read_note",
                "edit_note",
            )
        else:
            names = ("read_best_note", "read_note", "edit_note")
    else:
        names = (
            "list_vault",
            "find_note",
            "find_incomplete_tasks",
            "read_best_note",
            "read_note",
            "search_notes",
        )
    if re.search(r"\bskill\b", lower):
        names = tuple(names) + ("save_custom_skill",)
    else:
        try:
            from backend.skills.repeats import pending_skill_draft

            if pending_skill_draft():
                names = tuple(names) + ("save_custom_skill",)
        except Exception:
            pass
    return [by_name[name] for name in names if name in by_name]


def _dispatch_tool(name: str, arguments: dict, user_message: str) -> str:
    """Run a tool with server-side authorization checks."""
    args = arguments or {}
    write_ok = user_grants_write(user_message)
    delete_ok = write_ok and bool(
        re.search(r"\b(delete|remove|erase)\b", effective_write_message(user_message).lower())
    )

    try:
        if name == "list_vault":
            return list_vault(args.get("path", ""))
        if name == "find_note":
            return find_note(args.get("query", ""))
        if name == "read_best_note":
            return read_best_note(args.get("query", ""))
        if name == "find_daily_note":
            return find_daily_note(args.get("day"))
        if name == "find_incomplete_tasks":
            return find_incomplete_tasks(
                day=args.get("day"),
                context=args.get("context", ""),
            )
        if name == "complete_task":
            query = args.get("query", "")
            source = effective_write_message(user_message)
            if (
                not str(query).strip()
                or is_write_consent_only(str(query))
                or _AUTHORIZE_RE.search(str(query))
            ):
                query = _extract_task_query(source) or query
            return complete_task(
                query=query,
                path=args.get("path", "") or "",
                day=args.get("day"),
                authorized=bool(args.get("authorized")),
                user_authorized=write_ok,
            )
        if name == "save_custom_skill":
            from backend.skills.custom import save_custom_skill

            return save_custom_skill(
                args.get("slug", ""),
                args.get("name", ""),
                args.get("description", ""),
                args.get("body", ""),
                overwrite=bool(args.get("overwrite")),
                authorized=bool(args.get("authorized")) and write_ok,
            )
        if name == "read_note":
            return read_note(args.get("path", ""))
        if name == "search_notes":
            return search_notes(args.get("query", ""))
        if name == "edit_note":
            return edit_note(
                path=args.get("path", ""),
                new_content=args.get("new_content", ""),
                mode=args.get("mode", "replace"),
                authorized=bool(args.get("authorized")),
                user_authorized=write_ok,
            )
        if name == "create_note":
            return create_note(
                path=args.get("path", ""),
                content=args.get("content", ""),
                authorized=bool(args.get("authorized")),
                user_authorized=write_ok,
            )
        if name == "create_daily_note":
            return create_daily_note(
                day=args.get("day", "today"),
                content=args.get("content", ""),
                authorized=bool(args.get("authorized")),
                user_authorized=write_ok,
            )
        if name == "delete_note":
            return delete_note(
                path=args.get("path", ""),
                authorized=bool(args.get("authorized")),
                user_authorized=delete_ok,
            )
        return f"Unknown tool: {name}"
    except VaultAccessError as exc:
        return f"REFUSED: {exc}"
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return f"Error: {exc}"


def dispatch_tool(name: str, arguments: dict, user_message: str) -> str:
    """Run a tool and record retrieval/write latency."""
    started = time.perf_counter()
    try:
        result = _dispatch_tool(name, arguments, user_message)
        if name in {
            "complete_task",
            "edit_note",
            "create_note",
            "create_daily_note",
            "delete_note",
        } and str(result).startswith("OK:"):
            clear_pending_write()
        return result
    finally:
        logger.info(
            "PERF: tool name=%s total=%.3fs",
            name,
            time.perf_counter() - started,
        )
