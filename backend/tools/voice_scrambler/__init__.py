"""Live mic → anonymizing scramble → virtual output (BlackHole → Zoom/Discord)."""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

from backend.config import DATA_DIR
from backend.tools.voice_scrambler.dsp import FiveStrandProcessor, ScramblerSettings

logger = logging.getLogger(__name__)

_PREFS_PATH = DATA_DIR / "scrambler_prefs.json"
_SAMPLE_RATE = 16000
_BLOCK = 256  # ~16 ms @ 16 kHz — keep under ~20–30 ms total latency
_CHANNELS = 1

_VIRTUAL_HINTS = (
    "blackhole",
    "soundflower",
    "vb-cable",
    "vb cable",
    "cable",
    "loopback",
    "virtual",
    "aggregate",
    "multi-output",
    "multi output",
    "zoomaudio",
)
_SPEAKER_HINTS = (
    "speaker",
    "headphone",
    "built-in output",
    "built-in",
    "macbook",
    "display audio",
    "airpods",
    "earpods",
    "boom",
    "hdmi",
)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "scrambler_start",
            "description": (
                "Start the voice scrambler: capture the microphone, anonymize speech "
                "with a five-strand pitch/formant mix, and send it to a virtual output "
                "device (e.g. BlackHole) that meeting apps use as their microphone. "
                "Do not play to loudspeakers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "output_device": {
                        "type": "string",
                        "description": "Output device name substring or numeric index.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrambler_stop",
            "description": "Stop the live voice scrambler if it is running.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrambler_status",
            "description": (
                "Report whether the voice scrambler is running and list available "
                "output devices (prefer virtual cables such as BlackHole)."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]

_SCRAMBLER_INTENT = re.compile(
    r"\b("
    r"voice\s+scrambler|"
    r"scrambl(?:e|er|ing)\s+(?:my\s+)?voice|"
    r"anonymous?\s+(?:mic|microphone|voice)|"
    r"anonymi[sz]e\s+(?:my\s+)?(?:mic|voice)|"
    r"(?:start|stop|enable|disable)\s+(?:the\s+)?(?:voice\s+)?scrambler"
    r")\b",
    re.I,
)

_lock = threading.Lock()
_engine: "ScramblerEngine | None" = None


def _load_prefs() -> dict[str, Any]:
    try:
        if _PREFS_PATH.is_file():
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _save_prefs(data: dict[str, Any]) -> None:
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        try:
            _PREFS_PATH.chmod(0o600)
        except OSError:
            pass
    except OSError:
        logger.debug("SCRAMBLER: could not save prefs", exc_info=True)


def load_scrambler_settings() -> ScramblerSettings:
    return ScramblerSettings.from_dict(_load_prefs().get("dsp"))


def save_scrambler_settings(patch: dict[str, Any] | None = None) -> ScramblerSettings:
    prefs = _load_prefs()
    current = ScramblerSettings.from_dict(prefs.get("dsp"))
    merged = {**current.to_dict(), **(patch or {})}
    settings = ScramblerSettings.from_dict(merged)
    prefs["dsp"] = settings.to_dict()
    _save_prefs(prefs)
    with _lock:
        if _engine and _engine.running:
            _engine.update_settings(settings)
    return settings


def reset_scrambler_settings() -> ScramblerSettings:
    prefs = _load_prefs()
    settings = ScramblerSettings()
    prefs["dsp"] = settings.to_dict()
    _save_prefs(prefs)
    with _lock:
        if _engine and _engine.running:
            _engine.update_settings(settings)
    return settings


def _device_kind(name: str) -> str:
    lower = (name or "").lower()
    if any(h in lower for h in _VIRTUAL_HINTS):
        return "virtual"
    if any(h in lower for h in _SPEAKER_HINTS):
        return "speaker"
    return "other"


def list_output_devices() -> list[dict[str, Any]]:
    import sounddevice as sd

    devices = sd.query_devices()
    out: list[dict[str, Any]] = []
    for idx, info in enumerate(devices):
        if int(info.get("max_output_channels") or 0) <= 0:
            continue
        name = str(info.get("name") or f"Device {idx}")
        out.append(
            {
                "index": idx,
                "name": name,
                "channels": int(info.get("max_output_channels") or 0),
                "default": idx == sd.default.device[1],
                "kind": _device_kind(name),
            }
        )
    # Virtual cables first in the UI list.
    out.sort(key=lambda d: (0 if d["kind"] == "virtual" else 1, d["name"].lower()))
    return out


def _resolve_output_device(spec: str | None) -> tuple[int | None, str]:
    devices = list_output_devices()
    if not devices:
        return None, "No output devices found."

    prefs = _load_prefs()
    raw = (spec or "").strip() or str(prefs.get("output_device") or "").strip()

    if raw.isdigit():
        idx = int(raw)
        for d in devices:
            if d["index"] == idx:
                return idx, d["name"]
        return None, f"No output device with index {idx}."

    if raw:
        lower = raw.lower()
        for d in devices:
            if lower in d["name"].lower():
                return d["index"], d["name"]
        return None, f"No output device matching {raw!r}."

    # Prefer virtual loopback (BlackHole etc.) — never default to speakers.
    for d in devices:
        if d["kind"] == "virtual":
            return d["index"], d["name"]
    for d in devices:
        if d["kind"] != "speaker" and not d["default"]:
            return d["index"], d["name"]
    for d in devices:
        if d["kind"] != "speaker":
            return d["index"], d["name"]
    return None, (
        "No virtual audio device found. Install BlackHole (or similar), then select "
        "it as the scrambler output and set that device as the mic in Zoom/Discord. "
        "Marvin will not route scrambled audio to speakers by default."
    )


class ScramblerEngine:
    def __init__(
        self,
        output_device: int,
        output_name: str,
        settings: ScramblerSettings | None = None,
    ):
        self.output_device = output_device
        self.output_name = output_name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: str | None = None
        self._settings = settings or load_scrambler_settings()
        self._processor = FiveStrandProcessor(
            sample_rate=_SAMPLE_RATE, settings=self._settings
        )

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def update_settings(self, settings: ScramblerSettings) -> None:
        self._settings = settings
        self._processor.update_settings(settings)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._error = None
        self._processor.reset_state()
        self._thread = threading.Thread(target=self._run, name="voice-scrambler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        import sounddevice as sd

        try:
            with sd.Stream(
                samplerate=_SAMPLE_RATE,
                blocksize=_BLOCK,
                dtype="float32",
                channels=_CHANNELS,
                device=(None, self.output_device),
                latency="low",
            ) as stream:
                logger.info(
                    "SCRAMBLER: running out_device=%s (%s) block=%s",
                    self.output_device,
                    self.output_name,
                    _BLOCK,
                )
                while not self._stop.is_set():
                    indata, overflowed = stream.read(_BLOCK)
                    if overflowed:
                        logger.debug("SCRAMBLER: input overflow")
                    scrambled = self._processor.process(indata)
                    out = scrambled.reshape(-1, _CHANNELS)
                    stream.write(out)
        except Exception as exc:
            self._error = str(exc)
            logger.exception("SCRAMBLER: stream failed")
        finally:
            logger.info("SCRAMBLER: stopped")


def tools_for_scrambler() -> list[dict[str, Any]]:
    return list(TOOL_DEFINITIONS)


def decide_scrambler(user_message: str, *, available: bool = True) -> bool:
    text = (user_message or "").strip()
    if not text or not available:
        return False
    return bool(_SCRAMBLER_INTENT.search(text))


_STOP_RE = re.compile(
    r"\b(stop|disable|turn\s+off|end|quit)\b.*\b(scrambl|anonymous|anonymi)",
    re.I,
)
_STOP_RE_ALT = re.compile(
    r"\b(scrambl|anonymous|anonymi).*\b(stop|disable|turn\s+off|off)\b",
    re.I,
)
_STATUS_RE = re.compile(
    r"\b(status|is\s+(?:it|the\s+scrambler)\s+running|which\s+device)\b",
    re.I,
)


def handle_direct_scrambler(user_message: str) -> str | None:
    """
    Deterministic start/stop/status for clear spoken requests.

    Avoids depending on a cloud LLM tool round-trip for unambiguous phrases
    like \"scramble my voice\".
    """
    if not decide_scrambler(user_message):
        return None
    text = user_message or ""
    if _STOP_RE.search(text) or _STOP_RE_ALT.search(text):
        return stop_scrambler()
    if _STATUS_RE.search(text) and not re.search(
        r"\b(start|enable|scramble)\b", text, re.I
    ):
        return dispatch_scrambler_tool("scrambler_status", {}, text)
    device = None
    named = re.search(
        r"\b(?:on|to|via|using)\s+([A-Za-z0-9][A-Za-z0-9 _-]{1,40})",
        text,
        re.I,
    )
    if named:
        candidate = named.group(1).strip()
        if candidate.lower() not in {"my", "the", "a", "an", "voice", "mic"}:
            device = candidate
    return start_scrambler(device)


def scrambler_status_payload() -> dict[str, Any]:
    with _lock:
        eng = _engine
        running = bool(eng and eng.running)
        err = eng._error if eng else None
        out_name = eng.output_name if eng else _load_prefs().get("output_device_name")
        out_idx = eng.output_device if eng else _load_prefs().get("output_device_index")
    settings = load_scrambler_settings()
    devices = list_output_devices()
    has_virtual = any(d.get("kind") == "virtual" for d in devices)
    return {
        "running": running,
        "output_device": out_name,
        "output_device_index": out_idx,
        "error": err,
        "devices": devices,
        "settings": settings.to_dict(),
        "resolved": settings.resolved(),
        "has_virtual_device": has_virtual,
        "hint": (
            "Install BlackHole (or another virtual cable), select it as Output, start "
            "the scrambler, then set that cable as the microphone in Zoom/Discord. "
            "Audio is not played to speakers and is not saved."
            if not has_virtual
            else "Select a virtual cable (BlackHole) as output, start the scrambler, "
            "and set that cable as the mic in your meeting app. Raw audio is not saved."
        ),
    }


def start_scrambler(output_device: str | None = None) -> str:
    global _engine
    idx, name = _resolve_output_device(output_device)
    if idx is None:
        return name
    if _device_kind(name) == "speaker":
        return (
            f"Refusing to start on speaker-like device “{name}”. "
            "Choose BlackHole (or another virtual cable) so meeting apps can use "
            "the scrambled stream as their microphone."
        )
    settings = load_scrambler_settings()
    with _lock:
        if _engine and _engine.running:
            if _engine.output_device == idx:
                return f"Voice scrambler already running → { _engine.output_name }."
            _engine.stop()
        eng = ScramblerEngine(idx, name, settings=settings)
        eng.start()
        _engine = eng
    prefs = _load_prefs()
    prefs["output_device"] = str(idx)
    prefs["output_device_name"] = name
    prefs["output_device_index"] = idx
    prefs["dsp"] = settings.to_dict()
    _save_prefs(prefs)
    return (
        f"Voice scrambler started → “{name}”. "
        "Set that device as the microphone in Zoom/Discord (or use Multi-Output)."
    )


def stop_scrambler() -> str:
    global _engine
    with _lock:
        if not _engine or not _engine.running:
            return "Voice scrambler is not running."
        _engine.stop()
        _engine = None
    return "Voice scrambler stopped."


def shutdown_scrambler() -> None:
    """Best-effort stop on app exit."""
    try:
        stop_scrambler()
    except Exception:
        logger.debug("SCRAMBLER: shutdown failed", exc_info=True)


def dispatch_scrambler_tool(
    name: str,
    args: dict,
    user_message: str,
    *,
    cancellation_event: threading.Event | None = None,
) -> str:
    del user_message
    if cancellation_event is not None and cancellation_event.is_set():
        return "Scrambler request canceled."
    try:
        if name == "scrambler_start":
            return start_scrambler(str(args.get("output_device") or "") or None)
        if name == "scrambler_stop":
            return stop_scrambler()
        if name == "scrambler_status":
            status = scrambler_status_payload()
            devices = status.get("devices") or []
            names = ", ".join(
                f"{d['index']}:{d['name']}"
                + ("*" if d.get("default") else "")
                + (f"[{d.get('kind')}]" if d.get("kind") else "")
                for d in devices[:12]
            )
            state = "running" if status.get("running") else "stopped"
            target = status.get("output_device") or "unset"
            return (
                f"Scrambler {state}; output={target}. "
                f"Devices: {names or 'none'}. {status.get('hint')}"
            )
        return f"Unknown scrambler tool: {name}"
    except Exception:
        logger.exception("SCRAMBLER: tool failed name=%s", name)
        return "Could not complete that scrambler request."
