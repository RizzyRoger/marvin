"""Marvin agent — orchestrates the voice pipeline and function routing."""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date
from enum import Enum
from typing import Callable

import numpy as np
import sounddevice as sd

from backend.clock import get_clock_service, match_deterministic_datetime_query
from backend.config import (
    ENROLL_NATURAL_PROMPT,
    FUNCTION_VOICE_ALIASES,
    FUNCTIONS,
    SPEAKER_ENROLL_SECONDS,
    SPEAKER_LOCK_ENABLED,
    SPEAKER_NATURAL_ENROLL_SECONDS,
    SPEAKER_THRESHOLD,
    SPEAKER_VERIFY_SECONDS,
    SYSTEM_PROMPTS,
    VAD_MIN_SILENCE_MS,
    VAD_SAMPLE_RATE,
    _TOOL_EVIDENCE_RULE,
    enrollment_phrases,
)
from backend.pipeline import KokoroTTS, SileroVAD, SpeakerVerifier, WhisperSTT
from backend.providers.session_llm import ProviderLLM
from backend.pipeline.tones import play_listening_off, play_listening_on, play_rejected
from backend.storage.chat import append_message, load_history
from backend.voice_settings import (
    VoiceListeningSettings,
    load_voice_settings,
    save_voice_settings,
    update_voice_settings,
)

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str, dict], None]
MessageCallback = Callable[[dict], None]


class AgentStatus(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


class MarvinAgent:
    """Core agent: mic → VAD → speaker lock → Whisper → Qwen → Kokoro → speakers."""

    def __init__(
        self,
        on_status: StatusCallback | None = None,
        on_message: MessageCallback | None = None,
    ):
        self.on_status = on_status or (lambda _s, _d: None)
        self.on_message = on_message or (lambda _message: None)
        self.on_broadcast: Callable[[str, dict], None] = lambda _e, _d: None
        self.active_function = "chat"
        self._last_routed_function = "chat"
        self._clock = get_clock_service()
        self._client_timezone: str | None = None
        self._vad: SileroVAD | None = None
        self._stt: WhisperSTT | None = None
        self._llm: ProviderLLM | None = None
        self._tts: KokoroTTS | None = None
        self._speaker: SpeakerVerifier | None = None
        self._listening = False
        self._listen_thread: threading.Thread | None = None
        self._listen_ready = threading.Event()
        self._utterance_lock = threading.Lock()
        self._llm_lock = threading.Lock()
        self._audio_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._tool_lock = threading.Lock()
        self._tool_serial = 0
        self.used_functions: list[str] = []
        self._sticky_tools: list[str] = []
        self._active_tool_calls: dict[str, dict[str, int]] = {}
        self._voice_settings = load_voice_settings()
        self._enrollment_phrases: list[str] = enrollment_phrases()
        self._active_enrollment_sample_id: str | None = None
        self._enrollment_cancel = threading.Event()
        self._last_from_voice = False

    def load_models(self) -> None:
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Silero VAD"})
        self._vad = SileroVAD()
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Whisper large-v3-turbo"})
        self._stt = WhisperSTT()
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Qwen3 4B Instruct"})
        self._llm = ProviderLLM(load_local=True)
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Kokoro-82M TTS"})
        try:
            self.reload_tts()
        except Exception:
            self._tts = KokoroTTS()
            logger.exception("Speech-settings TTS load failed; using default Kokoro voice")
        self._emit(AgentStatus.PROCESSING, {"step": "Loading speaker verification"})
        self._speaker = SpeakerVerifier()
        self._sync_voice_settings_with_profile()
        try:
            from backend.skills import get_skill_file_service

            get_skill_file_service().ensure_exists()
        except Exception:
            logger.exception("Could not ensure skill.md placeholder")
        # Move the first safe vault scan into startup instead of the first request.
        from backend.tools.obsidian import warm_note_cache

        warm_note_cache()
        ready_data: dict = {
            "ready": True,
            "voice_enrolled": self._speaker.is_enrolled,
            "voice_settings": self.voice_listening_status(),
        }
        self._emit(AgentStatus.IDLE, ready_data)

    def reload_tts(self) -> None:
        """Hot-reload Kokoro after Output Speech settings change."""
        from backend.config import KOKORO_VOICE_MAP
        from backend.speech_settings import load_speech_settings

        settings = load_speech_settings()
        voice, lang = KOKORO_VOICE_MAP.get(
            (settings.nationality, settings.gender),
            ("bm_george", "b"),
        )
        with self._audio_lock:
            self._tts = KokoroTTS(voice=voice, lang=lang)
            logger.info("TTS reloaded voice=%s lang=%s", voice, lang)

    @property
    def is_ready(self) -> bool:
        return all([self._vad, self._stt, self._llm, self._tts, self._speaker])

    @property
    def voice_enrolled(self) -> bool:
        return bool(self._speaker and self._speaker.is_enrolled)

    def _sync_voice_settings_with_profile(self) -> None:
        settings = load_voice_settings()
        enrolled = bool(self._speaker and self._speaker.is_enrolled)
        if enrolled:
            if settings.voice_profile_status in {"not_configured", "error"}:
                settings.voice_profile_status = (
                    "enabled" if settings.voice_lock_enabled else "disabled"
                )
            if self._speaker and self._speaker.model_version:
                settings.verifier_model_version = self._speaker.model_version
        else:
            settings.voice_profile_status = "not_configured"
            if settings.voice_lock_enabled:
                settings.voice_profile_status = "needs_reenrollment"
        self._voice_settings = save_voice_settings(settings)

    def voice_listening_settings(self) -> VoiceListeningSettings:
        return self._voice_settings

    def update_voice_listening_settings(self, **changes) -> dict:
        settings = update_voice_settings(**changes)
        self._voice_settings = settings
        self._sync_voice_settings_with_profile()
        return self.voice_listening_status()

    def voice_listening_status(self) -> dict:
        settings = self.voice_listening_settings()
        enrolled = bool(self._speaker and self._speaker.is_enrolled)
        if settings.voice_lock_enabled and not enrolled:
            status = "needs_reenrollment"
        elif enrolled and settings.voice_lock_enabled:
            status = "enabled"
        elif enrolled:
            status = "disabled"
        else:
            status = "not_configured"
        samples: list[dict] = []
        if self._speaker:
            samples = self._speaker.ensure_enrollment_slots(self._enrollment_phrases)
        return {
            "enrolled": enrolled,
            "pending": self._speaker.pending_count if self._speaker else 0,
            "required": self._speaker.required_samples if self._speaker else 6,
            "lock_enabled": settings.voice_lock_enabled,
            "voice_lock_enabled": settings.voice_lock_enabled,
            "voice_profile_status": status,
            "strictness_mode": settings.strictness_mode,
            "require_addressing": settings.require_addressing,
            "contextual_continuation_enabled": settings.contextual_continuation_enabled,
            "continuation_window_seconds": settings.continuation_window_seconds,
            "profile_name": settings.profile_name,
            "enrollment_completed_at": settings.enrollment_completed_at,
            "verifier_model_version": settings.verifier_model_version,
            "phrases": list(self._enrollment_phrases),
            "samples": samples,
            "active_enrollment_sample_id": self._active_enrollment_sample_id,
            "sample_seconds": SPEAKER_ENROLL_SECONDS,
            "natural_sample_seconds": SPEAKER_NATURAL_ENROLL_SECONDS,
            "natural_prompt": ENROLL_NATURAL_PROMPT,
            "instructions": (
                "Stop Voice first. Use the microphone normally used with Marvin. "
                "Sit at a normal speaking distance in a quiet room. Speak naturally — "
                "do not whisper or shout. Avoid TV, music, or other voices. Read each "
                "fixed sentence completely, then pause before the next recording. The "
                "natural-speech exercise is free speech in your own words — do not read "
                "that instruction aloud."
            ),
            "limitation": (
                "Voice Lock verifies live microphone similarity to your enrolled "
                "profile. Replay or spoofed audio is not fully prevented."
            ),
        }

    def voice_profile_status(self) -> dict:
        return self.voice_listening_status()

    def notify_broadcast(self, event: str, data: dict) -> None:
        try:
            self.on_broadcast(event, data)
        except Exception:
            logger.debug("Broadcast %s failed", event, exc_info=True)

    def set_client_timezone(self, timezone_id: str | None) -> None:
        value = (timezone_id or "").strip() or None
        self._clock.update_session_timezone(client_timezone=value)
        self._client_timezone = self._clock.session_timezone

    def _set_sticky_tools(self, names: list[str]) -> None:
        self._mark_tools_used(*names)

    def _tool_activity_payload(self) -> dict:
        with self._tool_lock:
            active_tools = sorted(
                name for name, calls in self._active_tool_calls.items() if calls
            )
            used = list(self.used_functions)
            sticky = list(self._sticky_tools)
        return {
            "active_tools": active_tools,
            "functions_used": used,
            "sticky_tools": sticky,
        }

    def _emit(self, status: AgentStatus | str, data: dict | None = None) -> None:
        payload = {**(data or {}), **self._tool_activity_payload()}
        self.on_status(str(status), payload)

    def clear_used_tools(self) -> None:
        """Empty the turn-scoped sidebar list (new prompt or clear history)."""
        with self._tool_lock:
            self._active_tool_calls = {}
            self._sticky_tools = []
            self.used_functions = []

    def _mark_tools_used(self, *tool_ids: str) -> None:
        """Light sidebar rows for this turn. Chat never appears."""
        with self._tool_lock:
            ordered = list(self._sticky_tools)
            for raw in tool_ids:
                name = self._normalize_tool_activity_name(raw)
                if name and name != "chat" and name not in ordered:
                    ordered.append(name)
            self._sticky_tools = ordered
            self.used_functions = list(ordered)

    def begin_tool(self, request_id: int, tool_name: str) -> str:
        activity_name = self._normalize_tool_activity_name(tool_name)
        with self._tool_lock:
            self._tool_serial += 1
            call_id = f"{activity_name}-{self._tool_serial}"
            bucket = self._active_tool_calls.setdefault(activity_name, {})
            bucket[call_id] = request_id
        if activity_name and activity_name != "chat":
            self._mark_tools_used(activity_name)
        label = {
            "obsidian": "Using Obsidian",
            "web_search": "Using Web Search",
            "spotify": "Using Spotify",
            "timers": "Using Timers",
            "ai_model": "Switching Model",
            "voice_scrambler": "Voice Scrambler",
            "python_runner": "Running Python",
        }.get(activity_name, f"Using {activity_name}")
        self._emit(
            AgentStatus.PROCESSING,
            {
                "step": label,
                "tool": tool_name,
                "tool_activity": activity_name,
                "tool_phase": "running",
                "tool_call_id": call_id,
                "request_id": request_id,
            },
        )
        return call_id

    def finish_tool(
        self,
        call_id: str,
        request_id: int,
        *,
        status: str = "succeeded",
    ) -> None:
        with self._tool_lock:
            activity_name = None
            for name, bucket in self._active_tool_calls.items():
                if call_id in bucket and bucket[call_id] == request_id:
                    activity_name = name
                    del bucket[call_id]
                    break
        if activity_name is None:
            return
        self._emit(
            AgentStatus.PROCESSING,
            {
                "step": "Thinking",
                "tool_activity": activity_name,
                "tool_phase": status,
                "tool_call_id": call_id,
                "request_id": request_id,
            },
        )

    def _tracked_tool_executor(self, execute_tool):
        def wrapped(name, arguments, user_message=""):
            call_id = self.begin_tool(0, name)
            try:
                result = execute_tool(name, arguments, user_message)
            except Exception:
                self.finish_tool(call_id, 0, status="failed")
                raise
            self.finish_tool(call_id, 0, status="succeeded")
            return result

        return wrapped

    def set_function(self, function_id: str) -> bool:
        enabled_ids = {f["id"] for f in FUNCTIONS if f["enabled"]}
        if function_id not in enabled_ids:
            return False
        self.active_function = function_id
        self._last_routed_function = function_id
        self._emit(AgentStatus.IDLE, {"function": function_id})
        return True

    def _normalize_tool_activity_name(self, tool_name: str) -> str:
        name = (tool_name or "").strip().lower()
        if name.startswith("obsidian.") or name in {
            "list_vault",
            "find_note",
            "read_best_note",
            "find_daily_note",
            "find_incomplete_tasks",
            "complete_task",
            "read_note",
            "search_notes",
            "edit_note",
            "create_note",
            "create_daily_note",
            "delete_note",
            "prefetch_read_request",
        }:
            return "obsidian"
        if name.startswith("web_search") or name in {"web_search", "web-search"}:
            return "web_search"
        if name.startswith("spotify") or name in {
            "spotify_now_playing",
            "spotify_playback",
            "spotify_search_play",
        }:
            return "spotify"
        if name.startswith("run_python") or name in {"run_python", "python_runner"}:
            return "python_runner"
        if name.startswith("timer_") or name in {
            "timer_start",
            "timer_cancel",
            "timer_adjust",
            "timer_pause",
            "timers",
        }:
            return "timers"
        if name == "switch_model" or name in {"ai_model", "model"}:
            return "ai_model"
        if name.startswith("scrambler_") or name in {
            "scrambler_start",
            "scrambler_stop",
            "scrambler_status",
            "voice_scrambler",
        }:
            return "voice_scrambler"
        return name or "obsidian"

    def detect_function_switch(self, text: str) -> str | None:
        """Check if user wants to switch function via voice."""
        lower = text.lower().strip()
        switch_patterns = [
            r"(?:switch to|open|go to|use|enable)\s+(.+)",
            r"(?:marvin,?\s+)?(.+)\s+mode",
        ]
        for pattern in switch_patterns:
            match = re.search(pattern, lower)
            if match:
                target = match.group(1).strip()
                for func_id, aliases in FUNCTION_VOICE_ALIASES.items():
                    if any(alias in target for alias in aliases):
                        if self.set_function(func_id):
                            return func_id
        return None

    @staticmethod
    def _has_request_after_switch(text: str, function_id: str) -> bool:
        """Detect a second request after a spoken mode-switch command."""
        lower = text.lower()
        aliases = FUNCTION_VOICE_ALIASES.get(function_id, [])
        for alias in sorted(aliases, key=len, reverse=True):
            alias_at = lower.find(alias)
            if alias_at < 0:
                continue
            tail = lower[alias_at + len(alias):].strip(" \t,;:!?.")
            if not tail or tail == "mode":
                return False
            if tail.startswith("mode"):
                tail = tail[4:].strip(" \t,;:!?.")
            return bool(tail)
        return False

    def _enrich_prompt(
        self,
        prompt: str,
        *,
        routed_function: str | None = None,
        user_text: str = "",
    ) -> str:
        """Append user skill.md and bundled Agent Skills when relevant."""
        function_id = routed_function or self.active_function
        enriched = prompt
        try:
            from backend.skills import get_skill_file_service

            status = get_skill_file_service().get_status()
            if status.get("configured"):
                skill_text = get_skill_file_service().read().strip()
                if skill_text:
                    enriched = (
                        f"{enriched}\n\nUser skill instructions (follow when relevant):\n"
                        f"{skill_text}"
                    )
        except Exception:
            logger.debug("SKILL: could not load skill.md", exc_info=True)
        try:
            from backend.skills import build_skills_prompt_section

            section = build_skills_prompt_section(
                routed_function=function_id,
                user_text=user_text,
            )
            if section:
                enriched = f"{enriched}\n\nBundled skills:\n{section}"
        except Exception:
            logger.debug("SKILL: could not load format skills", exc_info=True)
        return enriched

    def _system_prompt(self) -> str:
        base = SYSTEM_PROMPTS.get(self.active_function, SYSTEM_PROMPTS["chat"])
        return self._enrich_prompt(base, routed_function=self.active_function)

    def _route_function(self, text: str) -> tuple[str, str]:
        """
        Route obvious requests without a second LLM generation. Use Qwen's
        reflective classifier only when wording is genuinely ambiguous.
        """
        if self.active_function in {"obsidian", "voice_lock"}:
            return self.active_function, "selected"

        lower = text.lower()
        obsidian_markers = (
            "obsidian",
            "vault",
            "daily note",
            "my note",
            "my file",
            "my files",
            "my folder",
            "my folders",
            "my documents",
            "my document",
            "my journal",
            "my unit",
            "note called",
            "note named",
            "the note",
            "search my notes",
            "in my notes",
            "what did i write",
            "what have i written",
            "review my",
            "read my",
            "check my",
            "summarize my",
            "edit my",
            "update my",
            "create a note",
            "delete my",
            "check off",
            "check it off",
            "mark complete",
            "mark as done",
            "mark as complete",
            "complete the task",
        )
        if any(marker in lower for marker in obsidian_markers):
            return "obsidian", "fast"
        try:
            from backend.tools.obsidian import (
                is_write_consent_only,
                pending_write_message,
            )

            if is_write_consent_only(text) and pending_write_message():
                return "obsidian", "consent"
        except Exception:
            logger.debug("ROUTER: write-consent check failed", exc_info=True)

        voice_markers = (
            "voice lock",
            "voice profile",
            "enroll my voice",
            "recognize my voice",
            "speaker verification",
        )
        if any(marker in lower for marker in voice_markers):
            return "voice_lock", "fast"

        referential_markers = (
            "summarize it",
            "summary of it",
            "tell me about it",
            "its contents",
            "that file",
            "that note",
        )
        if (
            self._last_routed_function == "obsidian"
            and any(marker in lower for marker in referential_markers)
        ):
            return "obsidian", "context"

        ambiguous_actions = (
            "find",
            "look",
            "review",
            "read",
            "open",
            "search",
            "summary",
            "summarize",
            "contents",
        )
        if any(action in lower for action in ambiguous_actions) and (
            " my " in f" {lower} " or " it" in lower or " that" in lower
        ):
            assert self._llm
            return self._llm.route_intent(text), "reflective"

        return "chat", "fast"

    def _execute_any_tool(self, name: str, args: dict, user_message: str) -> str:
        if name == "web_search":
            from backend.tools.web_search import dispatch_web_search_tool

            return dispatch_web_search_tool(name, args, user_message)
        if name.startswith("spotify"):
            from backend.tools.spotify import dispatch_spotify_tool, unwrap_spotify_tool_text
            from backend.tools.spotify.types import SpotifyError

            try:
                result = dispatch_spotify_tool(name, args, user_message)
            except SpotifyError as exc:
                from backend.tools.spotify import user_facing_error as spotify_user_facing_error

                return (
                    f'<spotify_data untrusted="true">\n'
                    f"{spotify_user_facing_error(exc)}\n"
                    f"</spotify_data>"
                )
            unwrap_spotify_tool_text(result)
            return result
        if name == "run_python":
            from backend.tools.python_runner import dispatch_python_tool

            return dispatch_python_tool(name, args, user_message)
        if name.startswith("timer_"):
            from backend.tools.timers import dispatch_timer_tool

            return dispatch_timer_tool(name, args, user_message)
        if name == "switch_model":
            from backend.tools.ai_model import dispatch_switch_model

            result = dispatch_switch_model(name, args, user_message)
            try:
                from backend.provider_service import providers_status

                self.notify_broadcast("model_changed", providers_status())
            except Exception:
                logger.debug("model_changed broadcast failed", exc_info=True)
            return result
        if name.startswith("scrambler_"):
            from backend.tools.voice_scrambler import dispatch_scrambler_tool

            return dispatch_scrambler_tool(name, args, user_message)
        from backend.tools.obsidian import dispatch_tool as dispatch_obsidian_tool

        return dispatch_obsidian_tool(name, args, user_message)

    def _process_side_effect_tools(self, text: str, prompt: str) -> str:
        assert self._llm
        from backend.tools.spotify import (
            SpotifyDecision,
            decide_spotify,
            register_spotify_capability,
            tools_for_spotify,
        )
        from backend.tools.python_runner import (
            decide_python,
            register_python_capability,
            tools_for_python,
        )
        from backend.tools.timers import (
            decide_timer,
            register_timer_capability,
            tools_for_timers,
        )
        from backend.tools.ai_model import (
            decide_switch_model,
            tools_for_switch_model,
        )
        from backend.tools.voice_scrambler import (
            decide_scrambler,
            handle_direct_scrambler,
            tools_for_scrambler,
        )
        from backend.tools.web_search import (
            SearchDecision,
            decide_web_search,
            register_web_search_capability,
            run_planned_search,
            tools_for_web_search,
            wrap_search_results,
        )
        from backend.tools.web_search.types import WebSearchError
        from backend.tools.multi_tool import (
            collect_required_families,
            compose_prompt_blurb,
            compose_tools,
            prefixes_for_families,
            primary_family,
        )

        web_available = register_web_search_capability()
        spotify_available = register_spotify_capability()
        python_available = register_python_capability()
        timer_available = register_timer_capability()
        search_decision, search_reason = decide_web_search(
            text, available=web_available, vault_required=False
        )
        spotify_decision, _spotify_reason = decide_spotify(
            text, available=spotify_available
        )
        python_needed = decide_python(text, available=python_available)
        timer_needed = decide_timer(text, available=timer_available)
        switch_needed = decide_switch_model(text, available=True)
        scrambler_needed = decide_scrambler(text, available=True)
        logger.info(
            "DEV: search=%s spotify=%s python=%s timer=%s switch=%s scrambler=%s",
            search_decision.value,
            spotify_decision.value,
            python_needed,
            timer_needed,
            switch_needed,
            scrambler_needed,
        )

        sticky: list[str] = []
        if search_decision.value in {"required", "allowed"} and web_available:
            sticky.append("web_search")
        if spotify_decision == SpotifyDecision.REQUIRED and spotify_available:
            sticky.append("spotify")
        if scrambler_needed:
            sticky.append("voice_scrambler")
        if timer_needed and timer_available:
            sticky.append("timers")
        if switch_needed:
            sticky.append("ai_model")
        if python_needed and python_available:
            sticky.append("python_runner")
        if sticky:
            self._set_sticky_tools(sticky)

        execute = self._tracked_tool_executor(self._execute_any_tool)
        runtime_block = self._clock.create_turn_context(turn_id="chat").to_prompt_block()
        prompt = f"{prompt}\n\n{runtime_block}"

        if spotify_decision == SpotifyDecision.UNAVAILABLE:
            from backend.tools.spotify import spotify_status

            status = spotify_status()
            if not status.client_configured:
                return (
                    "Spotify isn’t configured. Set SPOTIFY_CLIENT_ID and restart Marvin."
                )
            return "Spotify isn’t connected. Open Settings to connect."

        if search_decision == SearchDecision.UNAVAILABLE:
            return (
                "Web Search is not configured, so I could not check current sources."
            )

        required_families = collect_required_families(
            spotify_required=(
                spotify_decision == SpotifyDecision.REQUIRED and spotify_available
            ),
            scrambler_needed=scrambler_needed,
            timer_needed=timer_needed and timer_available,
            switch_needed=switch_needed,
            python_needed=python_needed and python_available,
        )
        if required_families:
            pre_satisfied: list[str] = []
            direct_scrambler_reply = None
            if "scrambler" in required_families:
                direct_scrambler_reply = handle_direct_scrambler(text)
                if direct_scrambler_reply:
                    self._mark_tools_used("voice_scrambler")
                    pre_satisfied.append("scrambler")
            remaining = [f for f in required_families if f not in pre_satisfied]
            if remaining:
                composed = compose_tools(
                    remaining,
                    providers={
                        "spotify": tools_for_spotify,
                        "scrambler": tools_for_scrambler,
                        "timers": tools_for_timers,
                        "ai_model": tools_for_switch_model,
                        "python_runner": tools_for_python,
                    },
                )
                extra = compose_prompt_blurb(remaining)
                if direct_scrambler_reply:
                    extra += (
                        f" Voice scrambler already ran: {direct_scrambler_reply} "
                        "Do not call scrambler tools again."
                    )
                reply = self._llm.chat_with_tools(
                    text,
                    f"{prompt} {extra} {_TOOL_EVIDENCE_RULE}",
                    composed,
                    execute,
                    force_tool_use=True,
                    required_tool_prefixes=prefixes_for_families(remaining),
                    pre_satisfied_families=pre_satisfied,
                )
            else:
                reply = direct_scrambler_reply or "Done."
                self._llm.remember_exchange(text, reply)
            return reply

        if search_decision == SearchDecision.REQUIRED and web_available:
            try:
                search_response = run_planned_search(
                    text,
                    turn_id="chat",
                    generation_id="chat",
                )
            except WebSearchError as exc:
                from backend.tools.web_search import user_facing_error

                reply = user_facing_error(exc)
                self._llm.remember_exchange(text, reply)
                return reply
            self._mark_tools_used("web_search")
            return self._llm.chat_with_context(
                text,
                prompt
                + " Ground factual claims in the provided web evidence and cite "
                "source IDs like [S1]. Prefer concise spoken answers.",
                wrap_search_results(search_response),
            )

        if search_decision == SearchDecision.ALLOWED and web_available:
            return self._llm.chat_with_tools(
                text,
                prompt
                + " A web-search tool is available, but do not use it unless you "
                "cannot answer from stable knowledge.",
                tools_for_web_search(),
                execute,
                force_tool_use=False,
            )

        return self._llm.chat(text, prompt)

    def process_text(self, text: str) -> str:
        """Handle typed or transcribed user input."""
        if not self.is_ready:
            raise RuntimeError("Models not loaded")

        logger.info("USER: %s", text)
        from backend.tools.obsidian import remember_write_turn

        self.clear_used_tools()
        self._emit(AgentStatus.PROCESSING, {"step": "Thinking"})
        remember_write_turn(text)
        switched = self.detect_function_switch(text)
        if switched and not self._has_request_after_switch(text, switched):
            label = next(f["label"] for f in FUNCTIONS if f["id"] == switched)
            reply = f"Switched to {label} mode."
            user_entry = append_message("user", text, self.active_function)
            reply_entry = append_message("assistant", reply, self.active_function)
            self.on_message(user_entry)
            self.on_message(reply_entry)
            logger.info("MARVIN: %s", reply)
            return reply

        user_entry = append_message("user", text, self.active_function)
        self.on_message(user_entry)
        self._emit(AgentStatus.PROCESSING, {"step": "Thinking"})

        from backend.skills.repeats import try_save_pending_skill

        saved_skill = try_save_pending_skill(text)
        if saved_skill:
            if saved_skill.startswith("OK:"):
                reply = saved_skill[4:].strip()
                if reply and reply[0].islower():
                    reply = reply[0].upper() + reply[1:]
                if not reply.endswith("."):
                    reply += "."
            else:
                reply = saved_skill
            reply_entry = append_message("assistant", reply, self.active_function)
            self.on_message(reply_entry)
            logger.info("MARVIN: %s", reply)
            return reply

        lower_text = text.lower()
        if any(
            marker in lower_text
            for marker in (
                "voice lock",
                "voice profile",
                "enroll my voice",
                "recognize my voice",
                "speaker verification",
            )
        ):
            reply = (
                "Voice Lock is configured in Settings under Voice and Listening. "
                "Open Settings, then Voice Lock, to enroll or change it."
            )
            reply_entry = append_message("assistant", reply, self.active_function)
            self.on_message(reply_entry)
            if self._llm:
                self._llm.remember_exchange(text, reply)
            logger.info("MARVIN: %s", reply)
            return reply

        from backend.reminders import handle_reminder_utterance

        reminder_reply = handle_reminder_utterance(text)
        if reminder_reply:
            self._mark_tools_used("timers")
            if self._llm:
                self._llm.remember_exchange(text, reminder_reply)
            reply_entry = append_message("assistant", reminder_reply, "daily_planning")
            self.on_message(reply_entry)
            logger.info("MARVIN: %s", reminder_reply)
            return reminder_reply

        clock_kind = match_deterministic_datetime_query(text)
        if clock_kind is not None:
            ctx = self._clock.create_turn_context(turn_id="typed")
            if clock_kind == "date":
                reply = self._clock.answer_date(ctx)
            elif clock_kind == "time":
                reply = self._clock.answer_time(ctx, refresh=True)
            else:
                reply = self._clock.answer_date_time(ctx, refresh=True)
            if self._llm:
                self._llm.remember_exchange(text, reply)
            reply_entry = append_message("assistant", reply, "chat")
            self.on_message(reply_entry)
            logger.info("MARVIN: %s", reply)
            return reply

        assert self._llm
        with self._llm_lock:
            generation_started = time.perf_counter()
            if hasattr(self._llm, "begin_turn"):
                self._llm.begin_turn()
            routed_function, route_method = self._route_function(text)
            self._last_routed_function = routed_function
            logger.info("ROUTER: %s (%s)", routed_function, route_method)
            prompt = self._enrich_prompt(
                SYSTEM_PROMPTS.get(routed_function, SYSTEM_PROMPTS["chat"]),
                routed_function=routed_function,
                user_text=text,
            )

            if routed_function == "obsidian":
                from backend.tools.obsidian import (
                    dispatch_tool,
                    effective_write_message,
                    handle_direct_daily_note_create,
                    is_write_consent_only,
                    pending_write_message,
                    prefetch_read_request,
                    tools_for_request,
                    user_grants_write,
                )

                prompt += f" The current local date is {date.today().isoformat()}."

                write_requested = user_grants_write(text)
                if is_write_consent_only(text) and pending_write_message():
                    prompt += (
                        f" The user previously asked: {pending_write_message()}. "
                        "They now authorize that write. Call complete_task with "
                        "authorized=true and a query naming each item from that request."
                    )
                elif write_requested and (
                    "check off" in effective_write_message(text).lower()
                    or "authori" in text.lower()
                ):
                    prompt += (
                        " If they asked to check off / mark done or authorized the write, "
                        "call complete_task with authorized=true. Do not say you are "
                        "not authorized."
                    )
                retrieval_started = time.perf_counter()
                prefetched_context = prefetch_read_request(text)
                logger.info(
                    "PERF: obsidian_prefetch total=%.3fs hit=%s",
                    time.perf_counter() - retrieval_started,
                    prefetched_context is not None,
                )
                direct_write_reply = handle_direct_daily_note_create(text)
                if direct_write_reply is not None:
                    # Relative dates and canonical daily-note paths are deterministic;
                    # bypassing generation also prevents unrelated history leaking in.
                    self._mark_tools_used("obsidian")
                    self._emit(AgentStatus.PROCESSING, {"step": "Using Obsidian"})
                    reply = direct_write_reply
                    self._llm.remember_exchange(text, reply)
                elif prefetched_context is not None:
                    # Common reads need one retrieval plus one answer generation,
                    # rather than a model planning round followed by a final round.
                    self._mark_tools_used("obsidian")
                    self._emit(AgentStatus.PROCESSING, {"step": "Using Obsidian"})
                    reply = self._llm.chat_with_context(
                        text,
                        prompt,
                        prefetched_context,
                    )
                elif write_requested:
                    reply = self._llm.chat_with_tools(
                        text,
                        prompt
                        + " You MUST call the relevant vault tool before answering. "
                        "Never claim you cannot access notes when tools are available.",
                        tools_for_request(text),
                        self._tracked_tool_executor(dispatch_tool),
                        requires_successful_write=True,
                    )
                else:
                    # Capability questions do not need a filesystem tool call.
                    reply = self._llm.chat(text, prompt)
            else:
                reply = self._process_side_effect_tools(text, prompt)
            logger.info(
                "LATENCY: Qwen route+response %.2fs",
                time.perf_counter() - generation_started,
            )

        from backend.skills.repeats import maybe_propose_skill

        draft = maybe_propose_skill(text)
        if draft:
            reply = (
                f"{reply.rstrip()}\n\nYou've asked this a few times. "
                f"I can save a custom skill “{draft['name']}”: {draft['description']} "
                f"{draft['body']} Say yes or I authorise to save it."
            )

        reply_entry = append_message("assistant", reply, self.active_function)
        self.on_message(reply_entry)
        logger.info("MARVIN: %s", reply)
        return reply

    def process_and_speak(
        self,
        text: str,
        *,
        client_timezone: str | None = None,
        from_voice: bool = False,
    ) -> str:
        if client_timezone:
            self.set_client_timezone(client_timezone)
        self._last_from_voice = from_voice
        reply = self.process_text(text)
        self.speak(reply, from_voice=from_voice)
        return reply

    def speak(self, text: str, *, from_voice: bool | None = None) -> None:
        """Synthesize and play TTS audio, honoring Output Speech mode."""
        if not self._tts:
            return
        spoken_from_voice = self._last_from_voice if from_voice is None else from_voice
        try:
            from backend.speech_settings import load_speech_settings

            mode = load_speech_settings().mode
        except Exception:
            mode = "always_on"
        if mode == "always_off":
            return
        if mode == "voice_input_only" and not spoken_from_voice:
            return
        self._emit(AgentStatus.SPEAKING, {"text": text[:80]})
        tts_started = time.perf_counter()
        audio = self._tts.synthesize(text)
        logger.info(
            "LATENCY: Kokoro synthesis %.2fs",
            time.perf_counter() - tts_started,
        )
        if len(audio) == 0:
            self._emit_idle_or_listening()
            return
        with self._audio_lock:
            sd.stop()
            sd.play(audio, self._tts.sample_rate)
            sd.wait()
            if self._listening:
                # Confirms that the reply is finished and microphone listening resumed.
                play_listening_on()
        self._emit_idle_or_listening()

    def handle_utterance(self, audio: np.ndarray) -> str:
        """Full pipeline for one speech segment."""
        assert self._stt and self._llm and self._tts and self._speaker
        utterance_started = time.perf_counter()

        settings = self._voice_settings
        lock_on = bool(settings.voice_lock_enabled) if settings else SPEAKER_LOCK_ENABLED
        if lock_on and self._speaker.is_enrolled:
            speaker_started = time.perf_counter()
            verify_samples = int(VAD_SAMPLE_RATE * SPEAKER_VERIFY_SECONDS)
            accepted, score = self._speaker.is_owner(
                audio[:verify_samples],
                VAD_SAMPLE_RATE,
                strictness_mode=settings.strictness_mode if settings else "strict",
            )
            logger.info(
                "LATENCY: speaker verification %.2fs",
                time.perf_counter() - speaker_started,
            )
            if not accepted:
                logger.info("Rejected non-owner speech (score=%.3f)", score)
                self._emit(AgentStatus.LISTENING, {"rejected": True, "score": score})
                try:
                    with self._audio_lock:
                        play_rejected()
                except Exception:
                    logger.debug("Rejected tone failed", exc_info=True)
                self._emit_idle_or_listening()
                return ""

        self._emit(AgentStatus.PROCESSING, {"step": "Transcribing"})
        stt_started = time.perf_counter()
        text = self._stt.transcribe(audio, VAD_SAMPLE_RATE)
        logger.info(
            "LATENCY: Whisper %.2fs",
            time.perf_counter() - stt_started,
        )
        if not text:
            self._emit_idle_or_listening()
            return ""
        reply = self.process_text(text)
        self.speak(reply, from_voice=True)
        logger.info(
            "LATENCY: full voice turn %.2fs",
            time.perf_counter() - utterance_started,
        )
        return reply

    def _emit_idle_or_listening(self) -> None:
        if self._listening:
            self._emit(AgentStatus.LISTENING, {"continuous": True})
        else:
            self._emit(AgentStatus.IDLE, {})

    def _run_utterance(self, audio: np.ndarray) -> None:
        try:
            self.handle_utterance(audio)
        except Exception:
            logger.exception("Voice utterance failed")
            self._emit(AgentStatus.ERROR, {"error": "voice pipeline failed"})
            self._emit_idle_or_listening()

    def _queue_utterance(self, audio: np.ndarray) -> None:
        if not self._listening:
            return
        if not self._utterance_lock.acquire(blocking=False):
            logger.info("Skipping utterance — pipeline already busy")
            return

        thread = threading.Thread(target=self._utterance_worker, args=(audio,), daemon=True)
        thread.start()

    def _utterance_worker(self, audio: np.ndarray) -> None:
        try:
            self._run_utterance(audio)
        finally:
            self._utterance_lock.release()

    def record_enrollment_sample(
        self,
        seconds: float | None = None,
        sample_id: str | None = None,
    ) -> dict:
        """Record one enrollment clip from the microphone."""
        if not self._speaker:
            raise RuntimeError("Speaker model not loaded")
        if self._listening:
            raise RuntimeError("Stop Voice before enrolling")

        self._speaker.ensure_enrollment_slots(self._enrollment_phrases)
        target_id = sample_id or self._speaker.next_recordable_sample_id()
        if not target_id:
            raise RuntimeError("All enrollment samples are already accepted")
        sample = self._speaker.get_sample(target_id)
        if sample is None:
            raise KeyError(f"Unknown enrollment sample: {target_id}")
        phrase = sample["prompt_text"]
        is_natural = sample.get("prompt_type") == "natural"
        if seconds is not None:
            duration = seconds
        elif is_natural:
            duration = SPEAKER_NATURAL_ENROLL_SECONDS
        else:
            duration = SPEAKER_ENROLL_SECONDS
        min_seconds = 6.0 if is_natural else 2.0
        frames = int(VAD_SAMPLE_RATE * duration)
        self._enrollment_cancel.clear()
        self._active_enrollment_sample_id = target_id
        self._speaker.set_sample_status(target_id, "recording")
        self._emit(
            AgentStatus.LISTENING,
            {"enrolling": True, "seconds": duration, "sample_id": target_id},
        )
        try:
            with self._audio_lock:
                play_listening_on()
            audio = sd.rec(frames, samplerate=VAD_SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            with self._audio_lock:
                play_listening_off()
            mono = audio[:, 0] if audio.ndim > 1 else audio
            result = self._speaker.add_enrollment_sample(
                mono,
                VAD_SAMPLE_RATE,
                min_seconds=min_seconds,
                sample_id=target_id,
            )
        except Exception:
            self._speaker.set_sample_status(target_id, "needs_retry", "Recording failed")
            raise
        finally:
            self._active_enrollment_sample_id = None
            self._emit(AgentStatus.IDLE, {"enrolling": False})
        result["phrases"] = list(self._enrollment_phrases)
        result["phrase"] = phrase
        result.update(self.voice_listening_status())
        return result

    def finalize_voice_enrollment(self) -> dict:
        if not self._speaker:
            raise RuntimeError("Speaker model not loaded")
        result = self._speaker.finalize_enrollment()
        update_voice_settings(
            voice_lock_enabled=True,
            voice_profile_status="enabled",
            enrollment_completed_at=result.get("completed_at", ""),
            verifier_model_version=result.get("model_version", ""),
        )
        self._sync_voice_settings_with_profile()
        self._enrollment_phrases = enrollment_phrases()
        self._emit(
            AgentStatus.IDLE,
            {"voice_enrolled": True, "voice_settings": self.voice_listening_status()},
        )
        return {**result, **self.voice_listening_status()}

    def clear_voice_profile(self) -> None:
        if self._speaker:
            self._speaker.clear_profile()
            update_voice_settings(
                voice_lock_enabled=False,
                voice_profile_status="not_configured",
                enrollment_completed_at="",
            )
            self._sync_voice_settings_with_profile()
            self._enrollment_phrases = enrollment_phrases()
            self._emit(
                AgentStatus.IDLE,
                {
                    "voice_enrolled": False,
                    "voice_settings": self.voice_listening_status(),
                },
            )

    def reset_enrollment(self) -> dict:
        self._enrollment_cancel.set()
        if self._speaker:
            self._speaker.reset_enrollment()
        self._enrollment_phrases = enrollment_phrases()
        if self._speaker:
            self._speaker.ensure_enrollment_slots(self._enrollment_phrases)
        self._active_enrollment_sample_id = None
        return self.voice_listening_status()

    def reset_enrollment_sample(self, sample_id: str) -> dict:
        if not self._speaker:
            raise RuntimeError("Speaker model not loaded")
        self._speaker.ensure_enrollment_slots(self._enrollment_phrases)
        result = self._speaker.reset_enrollment_sample(sample_id)
        status = self.voice_listening_status()
        status.update(result)
        return status

    def test_voice_sample(self, seconds: float | None = None) -> dict:
        """Record a short clip and score it against the enrolled profile."""
        if not self._speaker:
            raise RuntimeError("Speaker model not loaded")
        if not self._speaker.is_enrolled:
            raise RuntimeError("Enroll a voice profile before testing")
        if self._listening:
            raise RuntimeError("Stop Voice before testing enrollment")
        duration = seconds if seconds is not None else 3.0
        frames = int(VAD_SAMPLE_RATE * duration)
        self._emit(AgentStatus.LISTENING, {"testing": True, "seconds": duration})
        try:
            with self._audio_lock:
                play_listening_on()
            audio = sd.rec(frames, samplerate=VAD_SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            with self._audio_lock:
                play_listening_off()
            mono = audio[:, 0] if audio.ndim > 1 else audio
            settings = self.voice_listening_settings()
            result = self._speaker.test_sample(
                mono,
                VAD_SAMPLE_RATE,
                strictness_mode=settings.strictness_mode,
            )
        finally:
            self._emit(AgentStatus.IDLE, {"testing": False})
        return result

    def start_listening(self) -> bool:
        """Begin microphone capture and report whether the stream opened."""
        with self._state_lock:
            if not self.is_ready or self._listening:
                return self._listening
            self._listening = True
            self._listen_ready.clear()

        # Finish the cue before opening PortAudio input; concurrent open/play can
        # trigger Internal PortAudio error -9986 on macOS.
        try:
            with self._audio_lock:
                play_listening_on()
        except Exception:
            logger.debug("Listening-on tone failed", exc_info=True)

        with self._state_lock:
            if not self._listening:
                return False
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()

        opened = self._listen_ready.wait(timeout=3.0)
        if not opened:
            logger.error("Microphone stream timed out while opening")
            self._listening = False
            return False
        return self._listening

    def stop_listening(self) -> None:
        """Stop microphone capture and wait for the input stream to close."""
        with self._state_lock:
            if not self._listening:
                return
            self._listening = False
            thread = self._listen_thread
            self._listen_thread = None

        if thread and thread.is_alive():
            thread.join(timeout=3.0)

        try:
            with self._audio_lock:
                play_listening_off()
        except Exception:
            logger.debug("Listening-off tone failed", exc_info=True)
        self._emit(AgentStatus.IDLE, {})

    def _listen_loop(self) -> None:
        """Capture audio, detect speech via VAD, process utterances."""
        assert self._vad
        block_size = 512
        buffer: list[np.ndarray] = []
        in_speech = False
        silence_blocks = 0
        max_silence_blocks = max(
            1,
            int(
                VAD_SAMPLE_RATE
                / block_size
                * (VAD_MIN_SILENCE_MS / 1000)
            ),
        )

        def callback(indata, _frames, _time, status):
            if status:
                logger.warning("Audio status: %s", status)
            if not self._listening or self._utterance_lock.locked():
                return

            chunk = indata[:, 0].copy()

            nonlocal in_speech, silence_blocks

            if self._vad.is_speech(chunk):
                if not in_speech:
                    in_speech = True
                    self._emit(AgentStatus.LISTENING, {})
                silence_blocks = 0
                buffer.append(chunk)
            elif in_speech:
                buffer.append(chunk)
                silence_blocks += 1
                if silence_blocks >= max_silence_blocks:
                    in_speech = False
                    silence_blocks = 0
                    audio = np.concatenate(buffer)
                    buffer.clear()
                    self._queue_utterance(audio)

        self._emit(AgentStatus.LISTENING, {"continuous": True})
        try:
            with sd.InputStream(
                samplerate=VAD_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=block_size,
                callback=callback,
            ):
                self._listen_ready.set()
                while self._listening:
                    sd.sleep(100)
        except Exception:
            logger.exception("Microphone stream failed")
            self._listening = False
            self._listen_ready.set()
            self._emit(AgentStatus.ERROR, {"error": "microphone failed"})
            self._emit(AgentStatus.IDLE, {})

    def sync_history_to_llm(self) -> None:
        """Load persisted chat into LLM context."""
        if not self._llm:
            return
        history = load_history()
        llm_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in history[-20:]
            if m["role"] in ("user", "assistant")
        ]
        self._llm.set_history(llm_messages)
