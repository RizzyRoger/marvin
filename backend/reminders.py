"""Local reminders and timers for Marvin (in-process, no external calendar)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

_STORE_PATH = DATA_DIR / "reminders.json"
_lock = threading.Lock()
_scheduler_started = False
_emit: Callable[[str, dict[str, Any]], None] | None = None

_MAX_DURATION = 24 * 3600.0

# Remind-me only — timer phrases go through LLM tools.
_REMIND = re.compile(r"\bremind me\b", re.I)
_DURATION = re.compile(
    r"\bin\s+(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
    re.I,
)
_MESSAGE = re.compile(
    r"remind me(?:\s+to)?\s+(.+?)(?:\s+in\s+\d|\s*$)",
    re.I,
)


@dataclass
class Reminder:
    id: str
    message: str
    fire_at: float  # unix; meaningful when not paused
    created_at: float
    fired: bool = False
    name: str = ""
    kind: str = "reminder"  # "timer" | "reminder"
    paused: bool = False
    remaining_seconds: float | None = None

    def display_name(self) -> str:
        return (self.name or self.message or "Timer").strip() or "Timer"


class TimerError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def set_reminder_emitter(callback: Callable[[str, dict[str, Any]], None] | None) -> None:
    global _emit
    _emit = callback


def humanize_duration(seconds: float) -> str:
    """Default timer name from length, e.g. '5 minutes'."""
    secs = max(1, int(round(float(seconds))))
    if secs < 60:
        unit = "second" if secs == 1 else "seconds"
        return f"{secs} {unit}"
    if secs < 3600:
        mins = max(1, int(round(secs / 60)))
        unit = "minute" if mins == 1 else "minutes"
        return f"{mins} {unit}"
    hours = secs / 3600.0
    if abs(hours - round(hours)) < 0.05:
        whole = int(round(hours))
        unit = "hour" if whole == 1 else "hours"
        return f"{whole} {unit}"
    return f"{hours:.1f} hours"


def _clamp_duration(seconds: float) -> float:
    return max(1.0, min(float(seconds), _MAX_DURATION))


def _load() -> list[Reminder]:
    if not _STORE_PATH.is_file():
        return []
    try:
        raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[Reminder] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            message = str(item.get("message") or "Reminder")
            name = str(item.get("name") or message)
            remaining = item.get("remaining_seconds")
            out.append(
                Reminder(
                    id=str(item["id"]),
                    message=message,
                    fire_at=float(item.get("fire_at") or 0.0),
                    created_at=float(item.get("created_at") or time.time()),
                    fired=bool(item.get("fired")),
                    name=name,
                    kind=str(item.get("kind") or "reminder"),
                    paused=bool(item.get("paused")),
                    remaining_seconds=(
                        float(remaining) if remaining is not None else None
                    ),
                )
            )
        except Exception:
            continue
    return out


def _save(items: list[Reminder]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in items]
    tmp = _STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(_STORE_PATH)


def _pending_active(items: list[Reminder], *, kind: str | None = None) -> list[Reminder]:
    now = time.time()
    out: list[Reminder] = []
    for item in items:
        if item.fired:
            continue
        if kind and item.kind != kind:
            continue
        if item.paused:
            out.append(item)
            continue
        if item.fire_at > now - 1:
            out.append(item)
    return out


def _serialize(item: Reminder) -> dict[str, Any]:
    remaining = item.remaining_seconds
    if not item.paused and not item.fired:
        remaining = max(0.0, item.fire_at - time.time())
    return {
        "id": item.id,
        "name": item.display_name(),
        "message": item.message,
        "kind": item.kind,
        "paused": item.paused,
        "fired": item.fired,
        "remaining_seconds": remaining,
        "fire_at": item.fire_at,
        "fire_at_iso": (
            datetime.fromtimestamp(item.fire_at, tz=timezone.utc).isoformat()
            if item.fire_at
            else ""
        ),
    }


def list_pending() -> list[dict[str, Any]]:
    with _lock:
        return [_serialize(r) for r in _pending_active(_load())]


def list_pending_timers() -> list[dict[str, Any]]:
    with _lock:
        return [_serialize(r) for r in _pending_active(_load(), kind="timer")]


def _match_timer(items: list[Reminder], name_or_id: str) -> Reminder:
    key = (name_or_id or "").strip().lower()
    if not key:
        pending = _pending_active(items, kind="timer")
        if len(pending) == 1:
            return pending[0]
        if not pending:
            raise TimerError("No active timers.")
        names = ", ".join(p.display_name() for p in pending)
        raise TimerError(f"Which timer? Active: {names}.")
    for item in _pending_active(items, kind="timer"):
        if item.id.lower() == key:
            return item
    for item in _pending_active(items, kind="timer"):
        label = item.display_name().lower()
        if key == label or key in label or label in key:
            return item
    raise TimerError(f"No active timer matched “{name_or_id.strip()}”.")


def start_timer(name: str | None, duration_seconds: float) -> Reminder:
    duration = _clamp_duration(duration_seconds)
    label = (name or "").strip() or humanize_duration(duration)
    reminder = Reminder(
        id=str(uuid.uuid4()),
        message=label,
        name=label,
        kind="timer",
        fire_at=time.time() + duration,
        created_at=time.time(),
        paused=False,
        remaining_seconds=None,
    )
    with _lock:
        items = _load()
        items.append(reminder)
        _save(items)
    _ensure_scheduler()
    logger.info(
        "TIMER: started id=%s duration=%.1fs name=%s",
        reminder.id,
        duration,
        label[:80],
    )
    return reminder


def cancel_timer(name_or_id: str = "") -> Reminder:
    with _lock:
        items = _load()
        target = _match_timer(items, name_or_id)
        items = [r for r in items if r.id != target.id]
        _save(items)
    logger.info("TIMER: canceled id=%s name=%s", target.id, target.display_name())
    return target


def adjust_timer(name_or_id: str, delta_seconds: float) -> Reminder:
    delta = float(delta_seconds)
    with _lock:
        items = _load()
        target = _match_timer(items, name_or_id)
        for item in items:
            if item.id != target.id:
                continue
            if item.paused:
                remaining = float(item.remaining_seconds or 0.0) + delta
                item.remaining_seconds = _clamp_duration(remaining)
            else:
                item.fire_at = time.time() + _clamp_duration(
                    (item.fire_at - time.time()) + delta
                )
            target = item
            break
        _save(items)
    logger.info(
        "TIMER: adjusted id=%s delta=%.1fs paused=%s",
        target.id,
        delta,
        target.paused,
    )
    return target


def pause_timer(name_or_id: str = "") -> Reminder:
    with _lock:
        items = _load()
        target = _match_timer(items, name_or_id)
        if target.paused:
            raise TimerError(f"Timer “{target.display_name()}” is already paused.")
        for item in items:
            if item.id != target.id:
                continue
            item.remaining_seconds = max(1.0, item.fire_at - time.time())
            item.paused = True
            target = item
            break
        _save(items)
    logger.info(
        "TIMER: paused id=%s remaining=%.1fs",
        target.id,
        target.remaining_seconds or 0.0,
    )
    return target


def resume_timer(name_or_id: str = "") -> Reminder:
    with _lock:
        items = _load()
        target = _match_timer(items, name_or_id)
        if not target.paused:
            raise TimerError(f"Timer “{target.display_name()}” is not paused.")
        for item in items:
            if item.id != target.id:
                continue
            remaining = _clamp_duration(float(item.remaining_seconds or 1.0))
            item.fire_at = time.time() + remaining
            item.paused = False
            item.remaining_seconds = None
            target = item
            break
        _save(items)
    logger.info("TIMER: resumed id=%s fire_at=%.1f", target.id, target.fire_at)
    return target


def parse_reminder_request(text: str) -> tuple[str, float] | None:
    """Return (message, delay_seconds) for remind-me requests only."""
    raw = (text or "").strip()
    if not raw or not _REMIND.search(raw):
        return None
    match = _DURATION.search(raw)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("sec"):
        delay = float(amount)
    elif unit.startswith("min"):
        delay = float(amount) * 60.0
    else:
        delay = float(amount) * 3600.0
    delay = _clamp_duration(delay)
    msg_match = _MESSAGE.search(raw)
    message = (msg_match.group(1).strip(" .,!") if msg_match else "") or "Reminder"
    message = _DURATION.sub("", message).strip(" .,!") or "Reminder"
    return message, delay


def create_reminder(message: str, delay_seconds: float) -> Reminder:
    label = message.strip() or "Reminder"
    reminder = Reminder(
        id=str(uuid.uuid4()),
        message=label,
        name=label,
        kind="reminder",
        fire_at=time.time() + _clamp_duration(delay_seconds),
        created_at=time.time(),
    )
    with _lock:
        items = _load()
        items.append(reminder)
        _save(items)
    _ensure_scheduler()
    logger.info(
        "REMINDER: created id=%s delay=%.1fs message=%s",
        reminder.id,
        delay_seconds,
        reminder.message[:80],
    )
    return reminder


def decide_reminder(user_message: str) -> bool:
    return parse_reminder_request(user_message) is not None


def handle_reminder_utterance(user_message: str) -> str | None:
    parsed = parse_reminder_request(user_message)
    if not parsed:
        return None
    message, delay = parsed
    reminder = create_reminder(message, delay)
    if delay < 90:
        when = f"in {int(delay)} seconds"
    elif delay < 3600:
        when = f"in {int(round(delay / 60))} minutes"
    else:
        when = f"in {delay / 3600:.1f} hours"
    return f"Okay — I’ll remind you {when}: {reminder.message}."


def format_timer_confirmation(action: str, item: Reminder) -> str:
    label = item.display_name()
    if action == "start":
        remaining = max(0.0, item.fire_at - time.time())
        return f"Started timer “{label}” for {humanize_duration(remaining)}."
    if action == "cancel":
        return f"Canceled timer “{label}”."
    if action == "pause":
        rem = float(item.remaining_seconds or 0.0)
        return f"Paused timer “{label}” with {humanize_duration(rem)} left."
    if action == "resume":
        rem = max(0.0, item.fire_at - time.time())
        return f"Resumed timer “{label}” with {humanize_duration(rem)} left."
    if action == "adjust":
        if item.paused:
            rem = float(item.remaining_seconds or 0.0)
        else:
            rem = max(0.0, item.fire_at - time.time())
        return f"Updated timer “{label}”; {humanize_duration(rem)} remaining."
    return f"Timer “{label}” updated."


def _fire_due() -> None:
    due: list[Reminder] = []
    with _lock:
        items = _load()
        now = time.time()
        changed = False
        for item in items:
            if item.fired or item.paused:
                continue
            if item.fire_at <= now:
                item.fired = True
                due.append(item)
                changed = True
        if changed:
            _save(items)
    for item in due:
        payload = {
            "id": item.id,
            "message": item.message,
            "name": item.display_name(),
            "kind": item.kind,
            "fire_at": item.fire_at,
        }
        logger.info("REMINDER: fired id=%s kind=%s", item.id, item.kind)
        if _emit is not None:
            try:
                _emit("reminder", payload)
            except Exception:
                logger.exception("REMINDER: emit failed")


def _scheduler_loop() -> None:
    while True:
        try:
            _fire_due()
        except Exception:
            logger.exception("REMINDER: scheduler tick failed")
        time.sleep(1.0)


def _ensure_scheduler() -> None:
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        thread = threading.Thread(
            target=_scheduler_loop, name="marvin-reminders", daemon=True
        )
        thread.start()
        _scheduler_started = True
        logger.info("REMINDER: scheduler started")


def start_reminder_scheduler(
    emitter: Callable[[str, dict[str, Any]], None] | None = None,
) -> None:
    if emitter is not None:
        set_reminder_emitter(emitter)
    _ensure_scheduler()
