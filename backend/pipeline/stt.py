"""Whisper large-v3-turbo STT — transcribe speech to text (no raw audio saved)."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from backend.config import (
    MODELS_DIR,
    WHISPER_BEAM_SIZE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL_ID,
)

logger = logging.getLogger(__name__)


class WhisperSTT:
    """Speech-to-text using faster-whisper large-v3-turbo (int8 quantization)."""

    def __init__(self):
        local_path = MODELS_DIR / "whisper-large-v3-turbo"
        model_bin = local_path / "model.bin"
        model_path = str(local_path) if model_bin.exists() else WHISPER_MODEL_ID
        device = self._resolve_device()
        logger.info("Loading Whisper from %s on %s", model_path, device)
        self._model = WhisperModel(
            model_path,
            device=device,
            compute_type=WHISPER_COMPUTE_TYPE,
        )

    @staticmethod
    def _resolve_device() -> str:
        if WHISPER_DEVICE != "auto":
            return WHISPER_DEVICE
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe float32 mono audio; returns text only."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=WHISPER_BEAM_SIZE,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info("Transcribed: %r", text[:120])
        return text
