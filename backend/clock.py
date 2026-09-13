"""Trusted timezone-aware backend clock for Marvin turns."""

from __future__ import annotations

import json
import logging
import re
import threading
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.config import DATA_DIR, DEFAULT_USER_TIMEZONE

logger = logging.getLogger(__name__)

_ZONE_CACHE: dict[str, ZoneInfo] = {}
_ZONE_LOCK = threading.Lock()
_PREFS_LOCK = threading.Lock()
_PREFS_PATH = DATA_DIR / "user_prefs.json"

_turn_context: ContextVar["RuntimeDateTimeContext | None"] = ContextVar(
    "marvin_turn_clock_context",
    default=None,
)


@dataclass(frozen=True)
class RuntimeDateTimeContext:
    captured_at_utc: datetime
    local_datetime: datetime
    local_date: date
    local_time: str
    weekday: str
    timezone_id: str
    utc_offset: str
    timezone_abbreviation: str
    source: str
    turn_id: str
    used_fallback_timezone: bool = False

    def to_prompt_block(self) -> str:
        local_iso = self.local_datetime.isoformat()
        utc_iso = self.captured_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        return (
            "TRUSTED RUNTIME CONTEXT\n"
            f"- Current local datetime: {local_iso}\n"
            f"- Current local date: {self.local_date.isoformat()}\n"
            f"- Current local time: {self.local_time}\n"
            f"- Weekday: {self.weekday}\n"
            f"- Timezone: {self.timezone_id}\n"
            f"- UTC offset: {self.utc_offset}\n"
            f"- Current UTC datetime: {utc_iso}\n"
            f"- Source: {self.source}\n"
            f"- Reference turn ID: {self.turn_id}"
        )


class Clock(Protocol):
    def now_utc(self) -> datetime: ...


class SystemClock:
    """Wall-clock UTC source. Never use for latency measurements."""

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """Injectable frozen/advanceable clock for deterministic tests."""

    def __init__(self, instant: datetime):
        if instant.tzinfo is None:
            raise ValueError("FakeClock requires a timezone-aware datetime")
        self._instant = instant.astimezone(timezone.utc)

    def now_utc(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FakeClock requires a timezone-aware datetime")
        self._instant = instant.astimezone(timezone.utc)

    def advance(self, delta: timedelta) -> None:
        self._instant = self._instant + delta


def get_zoneinfo(timezone_id: str) -> ZoneInfo:
    key = (timezone_id or "").strip()
    with _ZONE_LOCK:
        cached = _ZONE_CACHE.get(key)
        if cached is not None:
            return cached
    try:
        zone = ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid timezone: {timezone_id}") from exc
    with _ZONE_LOCK:
        _ZONE_CACHE[key] = zone
    return zone


def load_saved_timezone() -> str | None:
    with _PREFS_LOCK:
        if not _PREFS_PATH.is_file():
            return None
        try:
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    value = (data.get("timezone") or "").strip()
    return value or None


def load_user_prefs() -> dict:
    with _PREFS_LOCK:
        return _load_user_prefs_unlocked()


def _load_user_prefs_unlocked() -> dict:
    if not _PREFS_PATH.is_file():
        return {}
    try:
        data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_user_prefs(updates: dict) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _PREFS_LOCK:
        payload = _load_user_prefs_unlocked()
        payload.update({k: v for k, v in updates.items() if v is not None})
        _PREFS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return dict(payload)


def load_saved_vault_root() -> str | None:
    value = (load_user_prefs().get("vault_root") or "").strip()
    return value or None


def save_vault_root(vault_root: str) -> str:
    path = Path(vault_root).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Vault path does not exist: {path}")
    save_user_prefs({"vault_root": str(path)})
    return str(path)


def save_timezone(timezone_id: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _PREFS_LOCK:
        payload = {"timezone": timezone_id}
        if _PREFS_PATH.is_file():
            try:
                existing = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    existing["timezone"] = timezone_id
                    payload = existing
            except (OSError, json.JSONDecodeError):
                pass
        _PREFS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def resolve_timezone_id(
    *,
    settings_timezone: str | None = None,
    client_timezone: str | None = None,
    default_timezone: str | None = None,
) -> tuple[str, bool]:
    """
    Resolve IANA timezone.

    Order: explicit settings → client-reported IANA → app default → UTC.
    Returns (timezone_id, used_fallback).
    """
    candidates = [
        (settings_timezone or "").strip(),
        (client_timezone or "").strip(),
        (default_timezone or DEFAULT_USER_TIMEZONE or "").strip(),
        "UTC",
    ]
    for index, candidate in enumerate(candidates):
        if not candidate:
            continue
        try:
            get_zoneinfo(candidate)
        except ValueError:
            logger.info("CLOCK: timezone_fallback invalid=%s", candidate)
            continue
        used_fallback = candidate == "UTC" and index > 0 and not any(
            c and c != "UTC" for c in candidates[:index]
        )
        # Disclose when we fell all the way to UTC because nothing else worked.
        if candidate == "UTC" and not any(
            (c and c != "UTC") for c in (settings_timezone, client_timezone, default_timezone)
        ):
            used_fallback = True
        logger.info("CLOCK: timezone_resolved timezone=%s", candidate)
        return candidate, used_fallback or (
            index > 0 and candidate == "UTC"
        )
    logger.info("CLOCK: timezone_fallback timezone=UTC")
    return "UTC", True


class ClockService:
    """Authoritative calendar clock used by agent, Obsidian, and Web Search."""

    def __init__(self, clock: Clock | None = None):
        self._clock = clock or SystemClock()
        self._session_timezone: str | None = load_saved_timezone()
        self._session_timezone_fallback = False

    def set_clock(self, clock: Clock) -> None:
        self._clock = clock

    def now_utc(self) -> datetime:
        instant = self._clock.now_utc()
        if instant.tzinfo is None:
            return instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(timezone.utc)

    def now_in_timezone(self, timezone_id: str) -> datetime:
        zone = get_zoneinfo(timezone_id)
        return self.now_utc().astimezone(zone)

    def update_session_timezone(
        self,
        *,
        settings_timezone: str | None = None,
        client_timezone: str | None = None,
    ) -> str:
        timezone_id, used_fallback = resolve_timezone_id(
            settings_timezone=settings_timezone or self._session_timezone,
            client_timezone=client_timezone,
            default_timezone=DEFAULT_USER_TIMEZONE,
        )
        if timezone_id != self._session_timezone:
            self._session_timezone = timezone_id
            try:
                save_timezone(timezone_id)
            except OSError:
                logger.info("CLOCK: timezone_persist_failed")
        self._session_timezone_fallback = used_fallback
        return timezone_id

    @property
    def session_timezone(self) -> str:
        return self._session_timezone or DEFAULT_USER_TIMEZONE or "UTC"

    def create_turn_context(
        self,
        *,
        turn_id: str,
        timezone_id: str | None = None,
        refresh: bool = False,
    ) -> RuntimeDateTimeContext:
        tz_id = timezone_id or self.session_timezone
        used_fallback = self._session_timezone_fallback
        try:
            local = self.now_in_timezone(tz_id)
        except ValueError:
            logger.info("CLOCK: timezone_fallback invalid=%s", tz_id)
            tz_id = "UTC"
            used_fallback = True
            local = self.now_in_timezone(tz_id)
        utc_now = local.astimezone(timezone.utc)
        offset = local.strftime("%z")
        offset_fmt = f"{offset[:3]}:{offset[3:]}" if offset else "+00:00"
        abbrev = local.tzname() or ("UTC" if tz_id == "UTC" else tz_id)
        context = RuntimeDateTimeContext(
            captured_at_utc=utc_now,
            local_datetime=local,
            local_date=local.date(),
            local_time=local.strftime("%H:%M:%S"),
            weekday=local.strftime("%A"),
            timezone_id=tz_id,
            utc_offset=offset_fmt,
            timezone_abbreviation=abbrev,
            source="trusted backend system clock",
            turn_id=str(turn_id),
            used_fallback_timezone=used_fallback,
        )
        logger.info(
            "CLOCK: turn_context_created local=%s timezone=%s weekday=%s turn=%s refresh=%s",
            local.isoformat(),
            tz_id,
            context.weekday,
            turn_id,
            refresh,
        )
        return context

    def format_date(self, context: RuntimeDateTimeContext) -> str:
        return context.local_datetime.strftime("%A, %B %-d, %Y")

    def format_time(self, context: RuntimeDateTimeContext) -> str:
        # %-I drops leading zero on Unix; fall back for platforms that reject it.
        try:
            return context.local_datetime.strftime("%-I:%M %p")
        except ValueError:
            return context.local_datetime.strftime("%I:%M %p").lstrip("0")

    def format_date_time(self, context: RuntimeDateTimeContext) -> str:
        return f"{self.format_date(context)} at {self.format_time(context)}"

    def answer_date(self, context: RuntimeDateTimeContext) -> str:
        return f"Today is {self.format_date(context)}."

    def answer_time(self, context: RuntimeDateTimeContext, *, refresh: bool = True) -> str:
        ctx = context
        if refresh:
            ctx = self.create_turn_context(
                turn_id=context.turn_id,
                timezone_id=context.timezone_id,
                refresh=True,
            )
        clock = self.format_time(ctx)
        if ctx.timezone_id == "UTC" or ctx.used_fallback_timezone:
            return f"It’s {clock} UTC."
        return f"It’s {clock} in your local time zone."

    def answer_date_time(self, context: RuntimeDateTimeContext, *, refresh: bool = True) -> str:
        ctx = context
        if refresh:
            ctx = self.create_turn_context(
                turn_id=context.turn_id,
                timezone_id=context.timezone_id,
                refresh=True,
            )
        return f"It’s {self.format_date(ctx)}, at {self.format_time(ctx)}."

    def resolve_relative_date(
        self,
        expression: str,
        reference: RuntimeDateTimeContext | None = None,
    ) -> date | None:
        text = (expression or "").strip().lower()
        ref = reference or get_turn_context()
        if ref is None:
            ref = self.create_turn_context(turn_id="relative")
        base = ref.local_date
        if text in {"today", "tonight", "this morning", "this afternoon", "this evening"}:
            resolved = base
        elif text == "tomorrow":
            resolved = base + timedelta(days=1)
        elif text == "yesterday":
            resolved = base - timedelta(days=1)
        elif text in {"this week"}:
            resolved = base
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            resolved = date.fromisoformat(text)
        else:
            match = re.fullmatch(r"(\d+)\s+days?\s+from\s+now", text)
            if match:
                resolved = base + timedelta(days=int(match.group(1)))
            else:
                return None
        logger.info(
            "CLOCK: relative_date_resolved expression=%s date=%s",
            text,
            resolved.isoformat(),
        )
        return resolved


_CLOCK_SERVICE = ClockService()


def get_clock_service() -> ClockService:
    return _CLOCK_SERVICE


def set_clock_service(service: ClockService) -> None:
    global _CLOCK_SERVICE
    _CLOCK_SERVICE = service


def set_turn_context(context: RuntimeDateTimeContext | None):
    return _turn_context.set(context)


def reset_turn_context(token) -> None:
    _turn_context.reset(token)


def get_turn_context() -> RuntimeDateTimeContext | None:
    return _turn_context.get()


def get_turn_local_date(fallback: date | None = None) -> date:
    ctx = get_turn_context()
    if ctx is not None:
        return ctx.local_date
    if fallback is not None:
        return fallback
    return get_clock_service().create_turn_context(turn_id="fallback").local_date


_DATETIME_ONLY = re.compile(
    r"^\s*(?:"
    r"(?:today[, ]+)?(?:what(?:'s| is|s)?\s+)?(?:the\s+)?date(?:\s+today)?(?:\s+today)?"
    r"|what(?:'s| is|s)?\s+today(?:'s)?\s+date"
    r"|tell me(?:\s+today(?:'s)?)?\s+date"
    r"|what(?:'s| is|s)?\s+(?:the\s+)?day(?:\s+of\s+the\s+week)?(?:\s+is\s+it)?"
    r"|what day is it"
    r"|what(?:'s| is|s)?\s+(?:the\s+)?time(?:\s+is\s+it)?"
    r"|what time is it(?:\s+right\s+now)?"
    r"|what(?:'s| is|s)?\s+(?:the\s+)?date(?:\s+and\s+time|\s+&\s+time)"
    r"|what(?:'s| is|s)?\s+(?:the\s+)?(?:date\s+and\s+time|time\s+and\s+date)"
    r")\s*[?.!]?\s*$",
    re.I,
)

_EXCLUDE_FROM_CLOCK = re.compile(
    r"\b("
    r"happened|news|tasks?|wrote|write|weather|meetings?|history|schedule|"
    r"obsidian|notes?|vault|search|price|version|president|ceo"
    r")\b",
    re.I,
)


def match_deterministic_datetime_query(text: str) -> str | None:
    """
    Return 'date', 'time', or 'datetime' for narrow clock-only questions.
    """
    cleaned = (text or "").strip()
    cleaned = (
        cleaned.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    if not cleaned or _EXCLUDE_FROM_CLOCK.search(cleaned):
        return None
    # Normalize common phrasing before matching.
    normalized = re.sub(r"\s+", " ", cleaned.lower()).strip(" ?!.")
    if re.fullmatch(
        r"(today[, ]+)?(what('s| is|s)? )?(the )?date( today)?( today)?|"
        r"what('s| is|s)? (the )?date( is it)?( today)?|"
        r"what('s| is|s)? today('s)? date|"
        r"tell me( today('s)?)? (the )?date|"
        r"what('s| is|s)? (the )?day( of the week)?( is it)?|"
        r"what day is it",
        normalized,
    ):
        return "date"
    if re.fullmatch(
        r"what('s| is|s)? (the )?time( is it)?( right now)?|"
        r"what time is it( right now)?",
        normalized,
    ):
        return "time"
    if re.fullmatch(
        r"what('s| is|s)? (the )?(date and time|time and date)",
        normalized,
    ):
        return "datetime"
    if _DATETIME_ONLY.match(cleaned):
        # Fallback for slight phrasing variants already covered above.
        lower = normalized
        if "time" in lower and "date" in lower:
            return "datetime"
        if "time" in lower:
            return "time"
        return "date"
    return None
