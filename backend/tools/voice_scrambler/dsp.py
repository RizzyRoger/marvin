"""Low-latency five-strand pitch/formant scrambler DSP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Clarity (0) ↔ Disguise (1) endpoint presets.
_CLARITY = {
    "pitch": [-3.0, -1.5, 0.0, 1.5, 3.0],
    "formant": [-1.0, -0.4, 0.2, 0.4, 1.0],
    "delay_ms": [0.0, 1.5, 3.0, 4.5, 6.0],
    "gain": [0.18, 0.22, 0.28, 0.22, 0.18],
    "mod_depth": 0.08,
    "wet": 0.72,
}
_DISGUISE = {
    "pitch": [-7.0, -3.0, 0.0, 3.0, 7.0],
    "formant": [-2.5, -1.0, 0.5, 1.0, 2.5],
    "delay_ms": [0.0, 3.0, 6.0, 9.0, 12.0],
    "gain": [0.22, 0.24, 0.12, 0.24, 0.22],
    "mod_depth": 0.22,
    "wet": 0.92,
}
_MOD_RATES_HZ = (0.11, 0.17, 0.09, 0.21, 0.14)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def interpolate_strand_params(clarity_disguise: float) -> dict[str, Any]:
    """Map Clarity↔Disguise (0=clarity … 1=disguise) to strand parameters."""
    t = float(np.clip(clarity_disguise, 0.0, 1.0))
    pitch = [_lerp(_CLARITY["pitch"][i], _DISGUISE["pitch"][i], t) for i in range(5)]
    formant = [
        _lerp(_CLARITY["formant"][i], _DISGUISE["formant"][i], t) for i in range(5)
    ]
    delay_ms = [
        _lerp(_CLARITY["delay_ms"][i], _DISGUISE["delay_ms"][i], t) for i in range(5)
    ]
    gain = [_lerp(_CLARITY["gain"][i], _DISGUISE["gain"][i], t) for i in range(5)]
    return {
        "pitch": pitch,
        "formant": formant,
        "delay_ms": delay_ms,
        "gain": gain,
        "mod_depth": _lerp(_CLARITY["mod_depth"], _DISGUISE["mod_depth"], t),
        "wet": _lerp(_CLARITY["wet"], _DISGUISE["wet"], t),
    }


@dataclass
class ScramblerSettings:
    """User-tunable scrambler controls (persisted in prefs)."""

    enabled_strength: float = 1.0  # scramble strength / wet scale
    clarity_disguise: float = 0.65  # 0 clarity … 1 disguise
    wet_dry: float | None = None  # override wet if set
    master_gain: float = 1.0
    mod_strength: float = 1.0
    pitch: list[float] | None = None
    formant: list[float] | None = None
    gain: list[float] | None = None
    delay_ms: list[float] | None = None

    def resolved(self) -> dict[str, Any]:
        base = interpolate_strand_params(self.clarity_disguise)
        if self.pitch and len(self.pitch) == 5:
            base["pitch"] = [float(x) for x in self.pitch]
        if self.formant and len(self.formant) == 5:
            base["formant"] = [float(x) for x in self.formant]
        if self.gain and len(self.gain) == 5:
            base["gain"] = [float(x) for x in self.gain]
        if self.delay_ms and len(self.delay_ms) == 5:
            base["delay_ms"] = [float(x) for x in self.delay_ms]
        wet = self.wet_dry if self.wet_dry is not None else base["wet"]
        wet = float(np.clip(wet * self.enabled_strength, 0.0, 1.0))
        base["wet"] = wet
        base["mod_depth"] = float(base["mod_depth"] * self.mod_strength)
        base["master_gain"] = float(self.master_gain)
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_strength": self.enabled_strength,
            "clarity_disguise": self.clarity_disguise,
            "wet_dry": self.wet_dry,
            "master_gain": self.master_gain,
            "mod_strength": self.mod_strength,
            "pitch": self.pitch,
            "formant": self.formant,
            "gain": self.gain,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScramblerSettings":
        data = data or {}

        def _five(key: str) -> list[float] | None:
            raw = data.get(key)
            if not isinstance(raw, (list, tuple)) or len(raw) != 5:
                return None
            try:
                return [float(x) for x in raw]
            except (TypeError, ValueError):
                return None

        wet = data.get("wet_dry")
        try:
            wet_f = float(wet) if wet is not None else None
        except (TypeError, ValueError):
            wet_f = None
        return cls(
            enabled_strength=float(data.get("enabled_strength", 1.0) or 1.0),
            clarity_disguise=float(data.get("clarity_disguise", 0.65) or 0.65),
            wet_dry=wet_f,
            master_gain=float(data.get("master_gain", 1.0) or 1.0),
            mod_strength=float(data.get("mod_strength", 1.0) or 1.0),
            pitch=_five("pitch"),
            formant=_five("formant"),
            gain=_five("gain"),
            delay_ms=_five("delay_ms"),
        )


def _pitch_shift_block(mono: np.ndarray, semitones: float) -> np.ndarray:
    """Cheap block pitch shift via resample + length fit (keeps consonants usable)."""
    n = mono.size
    if n < 8 or abs(semitones) < 1e-4:
        return mono
    ratio = float(2.0 ** (semitones / 12.0))
    new_len = max(8, int(round(n / max(ratio, 0.25))))
    t_old = np.linspace(0.0, 1.0, n, endpoint=False)
    t_new = np.linspace(0.0, 1.0, new_len, endpoint=False)
    stretched = np.interp(t_new, t_old, mono).astype(np.float32)
    if stretched.size != n:
        t_fit = np.linspace(0.0, 1.0, n, endpoint=False)
        t_src = np.linspace(0.0, 1.0, stretched.size, endpoint=False)
        stretched = np.interp(t_fit, t_src, stretched).astype(np.float32)
    return stretched


def _formant_shift_block(mono: np.ndarray, formant_semitones: float) -> np.ndarray:
    """
    Approximate formant shift with spectral envelope remapping.

    Positive values raise perceived vocal-tract resonances without a cartoon
    full pitch jump when combined with modest pitch strands.
    """
    n = mono.size
    if n < 32 or abs(formant_semitones) < 1e-4:
        return mono
    # Zero-pad to next power of two for stable FFT.
    nfft = 1 << int(np.ceil(np.log2(n)))
    window = np.hanning(n).astype(np.float32)
    framed = mono * window
    spec = np.fft.rfft(framed, n=nfft)
    mag = np.abs(spec)
    phase = np.angle(spec)
    factor = float(2.0 ** (formant_semitones / 12.0))
    bins = mag.size
    src = np.arange(bins, dtype=np.float32)
    dest = np.clip(src / max(factor, 0.25), 0, bins - 1)
    remapped = np.interp(src, dest, mag).astype(np.float32)
    # Preserve a little high-frequency consonant energy (mix dry HF).
    hf = int(bins * 0.55)
    remapped[hf:] = 0.65 * remapped[hf:] + 0.35 * mag[hf:]
    out = np.fft.irfft(remapped * np.exp(1j * phase), n=nfft).astype(np.float32)[:n]
    # Soft window compensation.
    denom = np.maximum(window, 1e-3)
    return (out / denom).astype(np.float32)


def _limiter(mono: np.ndarray, ceiling: float = 0.95) -> np.ndarray:
    peak = float(np.max(np.abs(mono))) or 1.0
    if peak <= ceiling:
        return mono
    return (mono * (ceiling / peak)).astype(np.float32)


@dataclass
class FiveStrandProcessor:
    """Stateful mic→scramble processor for one audio stream."""

    sample_rate: int = 16000
    settings: ScramblerSettings = field(default_factory=ScramblerSettings)
    _delay_bufs: list[np.ndarray] = field(default_factory=list)
    _delay_idx: list[int] = field(default_factory=list)
    _phase: list[float] = field(default_factory=list)
    _sample_count: int = 0

    def __post_init__(self) -> None:
        self.reset_state()

    def reset_state(self) -> None:
        # Up to ~20 ms delay at 16 kHz ≈ 320 samples; allocate comfortably.
        max_delay = max(64, int(0.05 * self.sample_rate))
        self._delay_bufs = [
            np.zeros(max_delay, dtype=np.float32) for _ in range(5)
        ]
        self._delay_idx = [0] * 5
        self._phase = [0.0] * 5
        self._sample_count = 0

    def update_settings(self, settings: ScramblerSettings) -> None:
        self.settings = settings

    def _read_delayed(self, strand: int, mono: np.ndarray, delay_samples: int) -> np.ndarray:
        buf = self._delay_bufs[strand]
        idx = self._delay_idx[strand]
        n = mono.size
        delay = int(np.clip(delay_samples, 0, buf.size - 1))
        # Write new samples into ring buffer, then gather delayed reads.
        end = idx + n
        if end <= buf.size:
            buf[idx:end] = mono
        else:
            first = buf.size - idx
            buf[idx:] = mono[:first]
            buf[: n - first] = mono[first:]
        positions = (np.arange(n) + idx - delay) % buf.size
        out = buf[positions].astype(np.float32, copy=True)
        self._delay_idx[strand] = end % buf.size
        return out

    def process(self, audio: np.ndarray) -> np.ndarray:
        mono = np.asarray(audio, dtype=np.float32).reshape(-1)
        if mono.size < 8:
            return mono
        params = self.settings.resolved()
        wet = float(params["wet"])
        master = float(params["master_gain"])
        mod_depth = float(params["mod_depth"])
        mixed = np.zeros_like(mono)
        t0 = self._sample_count / float(self.sample_rate)
        for i in range(5):
            # Slow LFO pitch wobble (±0.1–0.3 semitones scaled by mod_depth).
            lfo = np.sin(2.0 * np.pi * _MOD_RATES_HZ[i] * t0 + self._phase[i])
            mod = mod_depth * 0.25 * float(lfo)
            pitched = _pitch_shift_block(mono, float(params["pitch"][i]) + mod)
            formed = _formant_shift_block(pitched, float(params["formant"][i]))
            delay_samp = int(
                round(float(params["delay_ms"][i]) * self.sample_rate / 1000.0)
            )
            delayed = self._read_delayed(i, formed, delay_samp)
            mixed += delayed * float(params["gain"][i])
        dry_peak = float(np.max(np.abs(mono))) or 1.0
        wet_peak = float(np.max(np.abs(mixed))) or 1.0
        mixed *= dry_peak / wet_peak
        out = (1.0 - wet) * mono + wet * mixed
        out *= master
        # Preserve a little dry high-frequency energy for consonants (diff).
        if mono.size >= 8:
            hp = np.empty_like(mono)
            hp[0] = mono[0]
            hp[1:] = mono[1:] - 0.95 * mono[:-1]
            out = out + (0.1 * wet) * hp
        self._sample_count += mono.size
        return _limiter(out.astype(np.float32))
