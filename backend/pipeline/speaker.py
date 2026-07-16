"""SpeechBrain ECAPA-TDNN speaker verification — lock voice to enrolled owner."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch
import torchaudio

from backend.config import (
    SPEAKER_ENROLL_COUNT,
    SPEAKER_MODEL_ID,
    SPEAKER_PROFILE_PATH,
    SPEAKER_SAMPLE_RATE,
    SPEAKER_THRESHOLD,
)

logger = logging.getLogger(__name__)


class SpeakerVerifier:
    """Verify that speech belongs to the enrolled voice profile."""

    def __init__(self):
        from speechbrain.inference.speaker import EncoderClassifier

        logger.info("Loading SpeechBrain speaker encoder: %s", SPEAKER_MODEL_ID)
        self._classifier = EncoderClassifier.from_hparams(
            source=SPEAKER_MODEL_ID,
            savedir=str(Path.home() / ".cache" / "speechbrain" / "spkrec-ecapa-voxceleb"),
            run_opts={"device": "cpu"},
        )
        self._profile: np.ndarray | None = None
        self._pending: list[np.ndarray] = []
        self.load_profile()

    @property
    def is_enrolled(self) -> bool:
        return self._profile is not None

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def required_samples(self) -> int:
        return SPEAKER_ENROLL_COUNT

    def load_profile(self) -> bool:
        path = SPEAKER_PROFILE_PATH
        if not path.exists():
            self._profile = None
            return False
        data = np.load(path)
        emb = np.asarray(data["embedding"], dtype=np.float32)
        self._profile = emb / (np.linalg.norm(emb) + 1e-8)
        logger.info("Loaded voice profile from %s", path)
        return True

    def clear_profile(self) -> None:
        self._profile = None
        self._pending.clear()
        if SPEAKER_PROFILE_PATH.exists():
            SPEAKER_PROFILE_PATH.unlink()
        logger.info("Cleared voice profile")

    def reset_enrollment(self) -> None:
        self._pending.clear()

    def _to_tensor(self, audio: np.ndarray, sample_rate: int) -> torch.Tensor:
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        wav = torch.from_numpy(audio).unsqueeze(0)
        if sample_rate != SPEAKER_SAMPLE_RATE:
            wav = torchaudio.functional.resample(wav, sample_rate, SPEAKER_SAMPLE_RATE)
        return wav

    def embed(self, audio: np.ndarray, sample_rate: int = SPEAKER_SAMPLE_RATE) -> np.ndarray:
        wav = self._to_tensor(audio, sample_rate)
        with torch.no_grad():
            emb = self._classifier.encode_batch(wav)
        vec = emb.squeeze().cpu().numpy().astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-8)

    def add_enrollment_sample(self, audio: np.ndarray, sample_rate: int = SPEAKER_SAMPLE_RATE) -> dict:
        if len(audio) < sample_rate * 1.5:
            raise ValueError("Recording too short — speak for at least 2 seconds")
        emb = self.embed(audio, sample_rate)
        self._pending.append(emb)
        return {
            "pending": len(self._pending),
            "required": SPEAKER_ENROLL_COUNT,
            "ready": len(self._pending) >= SPEAKER_ENROLL_COUNT,
        }

    def finalize_enrollment(self) -> dict:
        if len(self._pending) < SPEAKER_ENROLL_COUNT:
            raise ValueError(
                f"Need {SPEAKER_ENROLL_COUNT} samples, have {len(self._pending)}"
            )
        mean = np.mean(np.stack(self._pending, axis=0), axis=0)
        mean = mean / (np.linalg.norm(mean) + 1e-8)
        SPEAKER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.savez(SPEAKER_PROFILE_PATH, embedding=mean)
        self._profile = mean
        self._pending.clear()
        logger.info("Saved voice profile (%d embeddings averaged)", SPEAKER_ENROLL_COUNT)
        return {"enrolled": True, "path": str(SPEAKER_PROFILE_PATH)}

    def score(self, audio: np.ndarray, sample_rate: int = SPEAKER_SAMPLE_RATE) -> float:
        if self._profile is None:
            return 1.0
        emb = self.embed(audio, sample_rate)
        return float(np.dot(self._profile, emb))

    def is_owner(
        self,
        audio: np.ndarray,
        sample_rate: int = SPEAKER_SAMPLE_RATE,
        threshold: float | None = None,
    ) -> tuple[bool, float]:
        """Return (accepted, similarity). If no profile, accepts everyone."""
        if self._profile is None:
            return True, 1.0
        if len(audio) < sample_rate * 0.4:
            return False, 0.0
        thresh = SPEAKER_THRESHOLD if threshold is None else threshold
        sim = self.score(audio, sample_rate)
        return sim >= thresh, sim
