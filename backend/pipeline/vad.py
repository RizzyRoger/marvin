"""Silero VAD — detect speech start/end in audio stream."""

from __future__ import annotations

import numpy as np
import torch

from backend.config import VAD_MIN_SILENCE_MS, VAD_SAMPLE_RATE, VAD_SPEECH_PAD_MS, VAD_THRESHOLD


class SileroVAD:
    """Wraps Silero VAD for streaming speech segment detection."""

    def __init__(self, threshold: float = VAD_THRESHOLD):
        self.threshold = threshold
        self.sample_rate = VAD_SAMPLE_RATE
        self._model, self._utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        (
            self._get_speech_timestamps,
            _,
            self._read_audio,
            *_,
        ) = self._utils

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Return True if the chunk contains speech."""
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        if audio_chunk.ndim > 1:
            audio_chunk = audio_chunk.mean(axis=1)
        tensor = torch.from_numpy(audio_chunk)
        prob = self._model(tensor, self.sample_rate).item()
        return prob >= self.threshold

    def extract_speech_segments(
        self,
        audio: np.ndarray,
        sample_rate: int = VAD_SAMPLE_RATE,
    ) -> list[np.ndarray]:
        """Return list of speech-only audio segments from a buffer."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        tensor = torch.from_numpy(audio)
        timestamps = self._get_speech_timestamps(
            tensor,
            self._model,
            sampling_rate=sample_rate,
            threshold=self.threshold,
            min_silence_duration_ms=VAD_MIN_SILENCE_MS,
            speech_pad_ms=VAD_SPEECH_PAD_MS,
        )
        segments = []
        for ts in timestamps:
            start = ts["start"]
            end = ts["end"]
            segments.append(audio[start:end])
        return segments
