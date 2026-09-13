"""Pinned model revisions and post-download integrity checks."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# Pin upstream revisions so release installs are reproducible.
WHISPER_REVISION = "main"
PIPER_REVISION = "master"
SILERO_VAD_REPO = "https://github.com/snakers4/silero-vad"
# Pinned tag/commit used for local (non-hub) Silero installs.
SILERO_VAD_REF = "v4.0"

# Minimum expected sizes (bytes) for critical artifacts — guards truncated downloads.
# Exact SHA256 entries can be added to MODEL_FILE_SHA256 as they are recorded.
MODEL_MIN_SIZES: dict[str, int] = {
    "whisper-large-v3-turbo/model.bin": 800_000_000,
    "piper/en/en_GB/alan/medium/en_GB-alan-medium.onnx": 50_000_000,
    "piper/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json": 1_000,
    "silero-vad/hubconf.py": 100,
}

# Optional exact digests (populate after a verified build). Empty = size-only check.
MODEL_FILE_SHA256: dict[str, str] = {}


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_models(models_dir: Path, *, required: Iterable[str] | None = None) -> list[str]:
    """
    Return a list of human-readable problems. Empty list means OK.
    """
    problems: list[str] = []
    keys = list(required) if required is not None else list(MODEL_MIN_SIZES.keys())
    for rel in keys:
        path = models_dir / rel
        if not path.is_file():
            problems.append(f"missing {rel}")
            continue
        size = path.stat().st_size
        minimum = MODEL_MIN_SIZES.get(rel, 1)
        if size < minimum:
            problems.append(f"too small {rel} ({size} < {minimum})")
            continue
        expected = MODEL_FILE_SHA256.get(rel)
        if expected:
            actual = sha256_file(path)
            if actual.lower() != expected.lower():
                problems.append(f"checksum mismatch {rel}")
                logger.error("MODEL: sha256 mismatch path=%s", rel)
    return problems


def assert_models_ok(models_dir: Path) -> None:
    problems = verify_models(models_dir)
    if problems:
        raise RuntimeError("Model verification failed: " + "; ".join(problems))
