"""SpeechBrain ECAPA-TDNN speaker verification — lock voice to enrolled owner."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchaudio

from backend.config import (
    ENROLL_NATURAL_PROMPT,
    SPEAKER_ENROLL_COUNT,
    SPEAKER_MODEL_ID,
    SPEAKER_PROFILE_PATH,
    SPEAKER_SAMPLE_RATE,
    SPEAKER_THRESHOLD,
)

logger = logging.getLogger(__name__)

_STRICTNESS_OFFSETS = {
    "balanced": -0.03,
    "strict": 0.0,
    "very_strict": 0.04,
}


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
        self._samples: list[dict[str, Any]] = []
        self._model_version = SPEAKER_MODEL_ID
        self.load_profile()

    @property
    def is_enrolled(self) -> bool:
        return self._profile is not None

    @property
    def pending_count(self) -> int:
        return len(self._accepted_embeddings())

    @property
    def required_samples(self) -> int:
        return SPEAKER_ENROLL_COUNT

    @property
    def model_version(self) -> str:
        return self._model_version

    def _accepted_embeddings(self) -> list[np.ndarray]:
        return [
            s["embedding"]
            for s in self._samples
            if s.get("status") == "accepted" and s.get("embedding") is not None
        ]

    def ensure_enrollment_slots(self, phrases: list[str]) -> list[dict[str, Any]]:
        """Create or refresh enrollment slots with stable sample IDs."""
        if self._samples and [s["prompt_text"] for s in self._samples] == list(phrases):
            return self.enrollment_samples_payload()
        previous = {
            s["prompt_text"]: s
            for s in self._samples
            if s.get("status") == "accepted" and s.get("embedding") is not None
        }
        slots: list[dict[str, Any]] = []
        for phrase in phrases:
            is_natural = phrase == ENROLL_NATURAL_PROMPT
            prior = previous.get(phrase)
            if prior is not None:
                slots.append(
                    {
                        "sample_id": prior["sample_id"],
                        "prompt_type": prior["prompt_type"],
                        "prompt_text": phrase,
                        "status": "accepted",
                        "embedding": prior["embedding"],
                        "quality_message": prior.get("quality_message") or "",
                    }
                )
            else:
                slots.append(
                    {
                        "sample_id": f"enroll-{uuid.uuid4().hex[:10]}",
                        "prompt_type": "natural" if is_natural else "phrase",
                        "prompt_text": phrase,
                        "status": "not_recorded",
                        "embedding": None,
                        "quality_message": "",
                    }
                )
        self._samples = slots
        return self.enrollment_samples_payload()

    def enrollment_samples_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "sample_id": s["sample_id"],
                "prompt_type": s["prompt_type"],
                "prompt_text": s["prompt_text"],
                "status": s["status"],
                "quality_message": s.get("quality_message") or "",
                "accepted": s["status"] == "accepted",
            }
            for s in self._samples
        ]

    def get_sample(self, sample_id: str) -> dict[str, Any] | None:
        for sample in self._samples:
            if sample["sample_id"] == sample_id:
                return sample
        return None

    def next_recordable_sample_id(self) -> str | None:
        for sample in self._samples:
            if sample["status"] in {"not_recorded", "needs_retry", "failed"}:
                return sample["sample_id"]
        return None

    def load_profile(self) -> bool:
        path = SPEAKER_PROFILE_PATH
        if not path.exists():
            self._profile = None
            return False
        data = np.load(path)
        emb = np.asarray(data["embedding"], dtype=np.float32)
        self._profile = emb / (np.linalg.norm(emb) + 1e-8)
        if "model_version" in data:
            try:
                self._model_version = str(np.asarray(data["model_version"]).item())
            except Exception:
                self._model_version = str(data["model_version"])
        logger.info("Loaded voice profile from %s", path)
        return True

    def clear_profile(self) -> None:
        self._profile = None
        self._samples.clear()
        if SPEAKER_PROFILE_PATH.exists():
            SPEAKER_PROFILE_PATH.unlink()
        logger.info("Cleared voice profile")

    def reset_enrollment(self) -> None:
        for sample in self._samples:
            sample["status"] = "not_recorded"
            sample["embedding"] = None
            sample["quality_message"] = ""
        logger.info("VOICE_PROFILE: enrollment_reset_all")

    def reset_enrollment_sample(self, sample_id: str) -> dict[str, Any]:
        sample = self.get_sample(sample_id)
        if sample is None:
            raise KeyError(f"Unknown enrollment sample: {sample_id}")
        sample["status"] = "not_recorded"
        sample["embedding"] = None
        sample["quality_message"] = ""
        logger.info("VOICE_PROFILE: enrollment_sample_reset id=%s", sample_id)
        return {
            "sample_id": sample_id,
            "pending": self.pending_count,
            "required": SPEAKER_ENROLL_COUNT,
            "ready": self.pending_count >= SPEAKER_ENROLL_COUNT,
            "samples": self.enrollment_samples_payload(),
        }

    def set_sample_status(self, sample_id: str, status: str, message: str = "") -> None:
        sample = self.get_sample(sample_id)
        if sample is None:
            return
        sample["status"] = status
        if message:
            sample["quality_message"] = message

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

    def _rms(self, audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))

    def validate_enrollment_audio(
        self,
        audio: np.ndarray,
        sample_rate: int = SPEAKER_SAMPLE_RATE,
        *,
        min_seconds: float = 2.0,
    ) -> None:
        if len(audio) < sample_rate * min_seconds:
            raise ValueError(
                f"Recording too short — speak for at least {int(min_seconds)} seconds"
            )
        rms = self._rms(audio)
        if rms < 0.01:
            raise ValueError("Recording too quiet — speak closer to the microphone")

    def add_enrollment_sample(
        self,
        audio: np.ndarray,
        sample_rate: int = SPEAKER_SAMPLE_RATE,
        *,
        min_seconds: float = 2.0,
        sample_id: str | None = None,
    ) -> dict:
        if not self._samples:
            logger.info("VOICE_PROFILE: enrollment_started")
        target_id = sample_id or self.next_recordable_sample_id()
        if not target_id:
            raise ValueError("All enrollment samples are already accepted")
        sample = self.get_sample(target_id)
        if sample is None:
            raise KeyError(f"Unknown enrollment sample: {target_id}")
        sample["embedding"] = None
        sample["status"] = "processing"
        sample["quality_message"] = ""
        try:
            self.validate_enrollment_audio(audio, sample_rate, min_seconds=min_seconds)
            emb = self.embed(audio, sample_rate)
            sample["embedding"] = emb
            sample["status"] = "accepted"
            sample["quality_message"] = "Accepted"
        except ValueError as exc:
            sample["embedding"] = None
            sample["status"] = "needs_retry"
            sample["quality_message"] = str(exc)
            raise
        return {
            "sample_id": target_id,
            "pending": self.pending_count,
            "required": SPEAKER_ENROLL_COUNT,
            "ready": self.pending_count >= SPEAKER_ENROLL_COUNT,
            "samples": self.enrollment_samples_payload(),
        }

    def finalize_enrollment(self) -> dict:
        pending = self._accepted_embeddings()
        if len(pending) < SPEAKER_ENROLL_COUNT:
            raise ValueError(
                f"Need {SPEAKER_ENROLL_COUNT} samples, have {len(pending)}"
            )
        mean = np.mean(np.stack(pending, axis=0), axis=0)
        mean = mean / (np.linalg.norm(mean) + 1e-8)
        SPEAKER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        completed_at = datetime.now(timezone.utc).isoformat()
        np.savez(
            SPEAKER_PROFILE_PATH,
            embedding=mean,
            model_version=np.asarray(SPEAKER_MODEL_ID),
            completed_at=np.asarray(completed_at),
        )
        self._profile = mean
        self._model_version = SPEAKER_MODEL_ID
        self._samples.clear()
        logger.info("Saved voice profile (%d embeddings averaged)", len(pending))
        return {
            "enrolled": True,
            "path": str(SPEAKER_PROFILE_PATH),
            "completed_at": completed_at,
            "model_version": SPEAKER_MODEL_ID,
        }

    def score(self, audio: np.ndarray, sample_rate: int = SPEAKER_SAMPLE_RATE) -> float:
        if self._profile is None:
            return 1.0
        emb = self.embed(audio, sample_rate)
        return float(np.dot(self._profile, emb))

    def threshold_for_mode(self, strictness_mode: str = "strict") -> float:
        return SPEAKER_THRESHOLD + _STRICTNESS_OFFSETS.get(strictness_mode, 0.0)

    def is_owner(
        self,
        audio: np.ndarray,
        sample_rate: int = SPEAKER_SAMPLE_RATE,
        threshold: float | None = None,
        *,
        strictness_mode: str | None = None,
    ) -> tuple[bool, float]:
        """Return (accepted, similarity). If no profile, accepts everyone."""
        if self._profile is None:
            return True, 1.0
        if len(audio) < sample_rate * 0.4:
            return False, 0.0
        if threshold is None and strictness_mode:
            threshold = self.threshold_for_mode(strictness_mode)
        thresh = SPEAKER_THRESHOLD if threshold is None else threshold
        sim = self.score(audio, sample_rate)
        return sim >= thresh, sim

    def test_sample(
        self,
        audio: np.ndarray,
        sample_rate: int = SPEAKER_SAMPLE_RATE,
        *,
        strictness_mode: str = "strict",
    ) -> dict:
        thresh = self.threshold_for_mode(strictness_mode)
        accepted, score = self.is_owner(
            audio,
            sample_rate,
            threshold=thresh,
        )
        if self._profile is None:
            reason = "no_profile"
        elif accepted:
            reason = "accepted"
        else:
            reason = "below_threshold"
        return {
            "accepted": accepted,
            "score": score,
            "reason": reason,
            "window_scores": [score],
            "threshold": thresh,
        }
