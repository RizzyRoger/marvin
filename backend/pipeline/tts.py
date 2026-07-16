"""Kokoro-82M TTS — synthesize speech with preset voice."""

from __future__ import annotations

import logging
import re

import numpy as np

from backend.config import KOKORO_LANG, KOKORO_SAMPLE_RATE, KOKORO_VOICE

logger = logging.getLogger(__name__)

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002700-\U000027BF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


class KokoroTTS:
    """Text-to-speech using Kokoro-82M."""

    def __init__(self, voice: str = KOKORO_VOICE, lang: str = KOKORO_LANG):
        from kokoro import KPipeline

        self.voice = voice
        self.sample_rate = KOKORO_SAMPLE_RATE
        logger.info("Loading Kokoro TTS (voice=%s, lang=%s)", voice, lang)
        self._pipeline = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        # Resolve the voice during startup so the first reply does not download/load it.
        self._voice_pack = self._pipeline.load_voice(voice)

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        text = _EMOJI_RE.sub("", text)
        return " ".join(text.split())

    def synthesize(self, text: str) -> np.ndarray:
        """Return float32 mono audio at 24 kHz."""
        text = self._clean_for_speech(text)
        if not text.strip():
            return np.array([], dtype=np.float32)

        chunks: list[np.ndarray] = []
        for _graphemes, _phonemes, audio in self._pipeline(
            text,
            voice=self._voice_pack,
            speed=1.0,
        ):
            chunks.append(np.asarray(audio, dtype=np.float32))

        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks)
