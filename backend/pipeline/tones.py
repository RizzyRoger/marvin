"""Short UI tones — listening on / listening off."""

from __future__ import annotations

import numpy as np
import sounddevice as sd

from backend.config import TONE_SAMPLE_RATE


def _tone(freqs: list[float], duration: float, volume: float = 0.22) -> np.ndarray:
    sr = TONE_SAMPLE_RATE
    t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    wave = np.zeros_like(t)
    for f in freqs:
        wave += np.sin(2 * np.pi * f * t)
    wave /= max(len(freqs), 1)
    # Soft attack/release to avoid clicks
    fade = int(0.01 * sr)
    if fade * 2 < len(wave):
        wave[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        wave[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return (wave * volume).astype(np.float32)


def play_listening_on() -> None:
    """Ascending chime — Marvin is listening."""
    audio = np.concatenate(
        [
            _tone([523.25], 0.08),  # C5
            np.zeros(int(0.02 * TONE_SAMPLE_RATE), dtype=np.float32),
            _tone([783.99], 0.12),  # G5
        ]
    )
    sd.play(audio, TONE_SAMPLE_RATE)
    sd.wait()


def play_listening_off() -> None:
    """Descending chime — Marvin stopped listening."""
    audio = np.concatenate(
        [
            _tone([783.99], 0.08),  # G5
            np.zeros(int(0.02 * TONE_SAMPLE_RATE), dtype=np.float32),
            _tone([392.00], 0.14),  # G4
        ]
    )
    sd.play(audio, TONE_SAMPLE_RATE)
    sd.wait()


def play_rejected() -> None:
    """Soft double-tap when a non-owner voice is ignored."""
    audio = np.concatenate(
        [
            _tone([220.0], 0.05, volume=0.12),
            np.zeros(int(0.04 * TONE_SAMPLE_RATE), dtype=np.float32),
            _tone([196.0], 0.06, volume=0.1),
        ]
    )
    sd.play(audio, TONE_SAMPLE_RATE)
    sd.wait()
