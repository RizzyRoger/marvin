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

from backend.config import (
    FUNCTION_VOICE_ALIASES,
    FUNCTIONS,
    SPEAKER_ENROLL_SECONDS,
    SPEAKER_LOCK_ENABLED,
    SPEAKER_VERIFY_SECONDS,
    SYSTEM_PROMPTS,
    VAD_MIN_SILENCE_MS,
    VAD_SAMPLE_RATE,
)
from backend.pipeline import KokoroTTS, QwenLLM, SileroVAD, SpeakerVerifier, WhisperSTT
from backend.pipeline.tones import play_listening_off, play_listening_on, play_rejected
from backend.storage.chat import append_message, load_history

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
        self.active_function = "chat"
        self._last_routed_function = "chat"
        self._vad: SileroVAD | None = None
        self._stt: WhisperSTT | None = None
        self._llm: QwenLLM | None = None
        self._tts: KokoroTTS | None = None
        self._speaker: SpeakerVerifier | None = None
        self._listening = False
        self._listen_thread: threading.Thread | None = None
        self._listen_ready = threading.Event()
        self._utterance_lock = threading.Lock()
        self._llm_lock = threading.Lock()
        self._audio_lock = threading.Lock()
        self._state_lock = threading.Lock()

    def load_models(self) -> None:
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Silero VAD"})
        self._vad = SileroVAD()
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Whisper large-v3-turbo"})
        self._stt = WhisperSTT()
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Qwen3 4B Instruct"})
        self._llm = QwenLLM()
        self._emit(AgentStatus.PROCESSING, {"step": "Loading Kokoro-82M TTS"})
        self._tts = KokoroTTS()
        self._emit(AgentStatus.PROCESSING, {"step": "Loading speaker verification"})
        self._speaker = SpeakerVerifier()
        # Move the first safe vault scan into startup instead of the first request.
        from backend.tools.obsidian import warm_note_cache

        warm_note_cache()
        ready_data: dict = {"ready": True, "voice_enrolled": self._speaker.is_enrolled}
        self._emit(AgentStatus.IDLE, ready_data)

    @property
    def is_ready(self) -> bool:
        return all([self._vad, self._stt, self._llm, self._tts, self._speaker])

    @property
    def voice_enrolled(self) -> bool:
        return bool(self._speaker and self._speaker.is_enrolled)

    def voice_profile_status(self) -> dict:
        if not self._speaker:
            return {"enrolled": False, "pending": 0, "required": 3, "lock_enabled": SPEAKER_LOCK_ENABLED}
        return {
            "enrolled": self._speaker.is_enrolled,
            "pending": self._speaker.pending_count,
            "required": self._speaker.required_samples,
            "lock_enabled": SPEAKER_LOCK_ENABLED,
        }

    def _emit(self, status: AgentStatus | str, data: dict | None = None) -> None:
        self.on_status(str(status), data or {})

    def set_function(self, function_id: str) -> bool:
        enabled_ids = {f["id"] for f in FUNCTIONS if f["enabled"]}
        if function_id not in enabled_ids:
            return False
        self.active_function = function_id
        self._last_routed_function = function_id
        self._emit(AgentStatus.IDLE, {"function": function_id})
        return True

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

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPTS.get(self.active_function, SYSTEM_PROMPTS["chat"])

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
        )
        if any(marker in lower for marker in obsidian_markers):
            return "obsidian", "fast"

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

    def process_text(self, text: str) -> str:
        """Handle typed or transcribed user input."""
        if not self.is_ready:
            raise RuntimeError("Models not loaded")

        logger.info("USER: %s", text)
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

        assert self._llm
        with self._llm_lock:
            generation_started = time.perf_counter()
            routed_function, route_method = self._route_function(text)
            self._last_routed_function = routed_function
            logger.info("ROUTER: %s (%s)", routed_function, route_method)
            prompt = SYSTEM_PROMPTS.get(routed_function, self._system_prompt())

            if routed_function == "obsidian":
                from backend.tools.obsidian import (
                    dispatch_tool,
                    handle_direct_daily_note_create,
                    prefetch_read_request,
                    tools_for_request,
                    user_grants_write,
                )

                prompt += f" The current local date is {date.today().isoformat()}."
                write_requested = user_grants_write(text)
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
                    reply = direct_write_reply
                    self._llm.remember_exchange(text, reply)
                elif prefetched_context is not None:
                    # Common reads need one retrieval plus one answer generation,
                    # rather than a model planning round followed by a final round.
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
                        dispatch_tool,
                        requires_successful_write=True,
                    )
                else:
                    # Capability questions do not need a filesystem tool call.
                    reply = self._llm.chat(text, prompt)
            else:
                reply = self._llm.chat(text, prompt)
            logger.info(
                "LATENCY: Qwen route+response %.2fs",
                time.perf_counter() - generation_started,
            )

        reply_entry = append_message("assistant", reply, self.active_function)
        self.on_message(reply_entry)
        logger.info("MARVIN: %s", reply)
        return reply

    def speak(self, text: str) -> None:
        """Synthesize and play TTS audio."""
        if not self._tts:
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

        if SPEAKER_LOCK_ENABLED and self._speaker.is_enrolled:
            speaker_started = time.perf_counter()
            verify_samples = int(VAD_SAMPLE_RATE * SPEAKER_VERIFY_SECONDS)
            accepted, score = self._speaker.is_owner(
                audio[:verify_samples],
                VAD_SAMPLE_RATE,
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
        self.speak(reply)
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

    def record_enrollment_sample(self, seconds: float | None = None) -> dict:
        """Record one enrollment clip from the microphone."""
        if not self._speaker:
            raise RuntimeError("Speaker model not loaded")
        if self._listening:
            raise RuntimeError("Stop Voice before enrolling")

        duration = seconds if seconds is not None else SPEAKER_ENROLL_SECONDS
        frames = int(VAD_SAMPLE_RATE * duration)
        self._emit(AgentStatus.LISTENING, {"enrolling": True, "seconds": duration})
        try:
            with self._audio_lock:
                play_listening_on()
            audio = sd.rec(frames, samplerate=VAD_SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            with self._audio_lock:
                play_listening_off()
            mono = audio[:, 0] if audio.ndim > 1 else audio
            result = self._speaker.add_enrollment_sample(mono, VAD_SAMPLE_RATE)
        finally:
            self._emit(AgentStatus.IDLE, {"enrolling": False})
        return result

    def finalize_voice_enrollment(self) -> dict:
        if not self._speaker:
            raise RuntimeError("Speaker model not loaded")
        result = self._speaker.finalize_enrollment()
        self._emit(AgentStatus.IDLE, {"voice_enrolled": True})
        return result

    def clear_voice_profile(self) -> None:
        if self._speaker:
            self._speaker.clear_profile()
            self._emit(AgentStatus.IDLE, {"voice_enrolled": False})

    def reset_enrollment(self) -> None:
        if self._speaker:
            self._speaker.reset_enrollment()

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
