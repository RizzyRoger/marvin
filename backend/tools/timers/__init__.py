"""Countdown timer tools for Marvin."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from backend.reminders import (
    TimerError,
    adjust_timer,
    cancel_timer,
    format_timer_confirmation,
    humanize_duration,
    list_pending_timers,
    pause_timer,
    resume_timer,
    start_timer,
)

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "timer_start",
            "description": (
                "Start a countdown timer. Pass duration_seconds from the user’s request. "
                "Optional name: use a contextual label if the user gave one (egg, workout); "
                "otherwise omit name so the default is the duration label (e.g. '5 minutes')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_seconds": {
                        "type": "number",
                        "description": "Countdown length in seconds (1 to 86400).",
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional timer name from context.",
                    },
                },
                "required": ["duration_seconds"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "timer_cancel",
            "description": "Cancel an active timer by name or id. Omit name if only one timer is active.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Timer name or id to cancel.",
                    },
                    "timer_id": {
                        "type": "string",
                        "description": "Timer id to cancel.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "timer_adjust",
            "description": (
                "Add or subtract time on an active timer. Positive delta_seconds adds time; "
                "negative subtracts. Omit name if only one timer is active."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "delta_seconds": {
                        "type": "number",
                        "description": "Seconds to add (positive) or subtract (negative).",
                    },
                    "name": {
                        "type": "string",
                        "description": "Timer name or id.",
                    },
                    "timer_id": {
                        "type": "string",
                        "description": "Timer id.",
                    },
                },
                "required": ["delta_seconds"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "timer_pause",
            "description": "Pause or resume an active timer. action is pause or resume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["pause", "resume"],
                        "description": "pause freezes the countdown; resume continues it.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Timer name or id.",
                    },
                    "timer_id": {
                        "type": "string",
                        "description": "Timer id.",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
]

_TIMER_INTENT = re.compile(
    r"\b("
    r"timer|"
    r"countdown|"
    r"set\s+(?:a\s+|an\s+)?(?:\d+\s*)?(?:minute|min|second|sec|hour|hr)s?\s+timer|"
    r"start\s+(?:a\s+|an\s+)?timer|"
    r"cancel\s+(?:the\s+|my\s+)?timer|"
    r"stop\s+(?:the\s+|my\s+)?timer|"
    r"pause\s+(?:the\s+|my\s+)?timer|"
    r"resume\s+(?:the\s+|my\s+)?timer|"
    r"unpause\s+(?:the\s+|my\s+)?timer|"
    r"(?:add|subtract|remove)\s+\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)\s+"
    r"(?:to|from|on)\s+(?:the\s+|my\s+)?timer|"
    r"(?:add|give)\s+(?:the\s+|my\s+)?timer\s+\d+"
    r")\b",
    re.I,
)

_REMIND_ME = re.compile(r"\bremind me\b", re.I)


def register_timer_capability() -> bool:
    try:
        from backend.config import DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def tools_for_timers() -> list[dict[str, Any]]:
    if not register_timer_capability():
        return []
    return list(TOOL_DEFINITIONS)


def decide_timer(user_message: str, *, available: bool = True) -> bool:
    text = (user_message or "").strip()
    if not text or not available:
        return False
    if _REMIND_ME.search(text) and not re.search(r"\btimer\b", text, re.I):
        return False
    return bool(_TIMER_INTENT.search(text))


def _resolve_name(args: dict) -> str:
    return str(args.get("timer_id") or args.get("name") or "").strip()


def dispatch_timer_tool(
    name: str,
    args: dict,
    user_message: str,
    *,
    cancellation_event: threading.Event | None = None,
) -> str:
    del user_message
    if cancellation_event is not None and cancellation_event.is_set():
        return "Timer request canceled."
    if not register_timer_capability():
        return "Timers are unavailable right now."

    try:
        if name == "timer_start":
            duration = float(args.get("duration_seconds") or 0)
            if duration <= 0:
                return "A positive duration_seconds is required to start a timer."
            label = str(args.get("name") or "").strip() or None
            item = start_timer(label, duration)
            return format_timer_confirmation("start", item)

        if name == "timer_cancel":
            item = cancel_timer(_resolve_name(args))
            return format_timer_confirmation("cancel", item)

        if name == "timer_adjust":
            if "delta_seconds" not in args:
                return "delta_seconds is required to adjust a timer."
            item = adjust_timer(_resolve_name(args), float(args.get("delta_seconds")))
            return format_timer_confirmation("adjust", item)

        if name == "timer_pause":
            action = str(args.get("action") or "pause").strip().lower()
            key = _resolve_name(args)
            if action == "resume":
                item = resume_timer(key)
                return format_timer_confirmation("resume", item)
            item = pause_timer(key)
            return format_timer_confirmation("pause", item)

        return f"Unknown timer tool: {name}"
    except TimerError as exc:
        pending = list_pending_timers()
        extra = ""
        if pending:
            names = ", ".join(p["name"] for p in pending)
            extra = f" Active timers: {names}."
        return f"{exc.message}{extra}"
    except Exception:
        logger.exception("TIMER: tool failed name=%s", name)
        return "Could not complete that timer request."


def default_name_for_duration(duration_seconds: float) -> str:
    return humanize_duration(duration_seconds)
