#!/usr/bin/env python3
"""Download all Marvin models: Whisper, Qwen3 4B, Kokoro, Silero VAD."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import (  # noqa: E402
    LLM_FILENAME,
    LLM_REPO,
    MODELS_DIR,
    WHISPER_MODEL_ID,
)


def download_whisper() -> None:
    from huggingface_hub import snapshot_download

    dest = MODELS_DIR / "whisper-large-v3-turbo"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Whisper large-v3-turbo → {dest}")
    snapshot_download(
        repo_id=WHISPER_MODEL_ID,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )
    print("✓ Whisper downloaded")


def download_llm() -> None:
    from huggingface_hub import hf_hub_download

    dest = MODELS_DIR / "llm"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Qwen3 4B Instruct Q4 → {dest}")
    hf_hub_download(
        repo_id=LLM_REPO,
        filename=LLM_FILENAME,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )
    print("✓ Qwen3 4B Instruct downloaded")


def download_silero_vad() -> None:
    import torch

    print("Downloading Silero VAD (via torch.hub)…")
    torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
    )
    print("✓ Silero VAD cached")


def download_kokoro() -> None:
    print("Downloading Kokoro-82M (British pipeline init)…")
    from kokoro import KPipeline

    KPipeline(lang_code="b", repo_id="hexgrad/Kokoro-82M")
    print("✓ Kokoro-82M cached")


def download_speaker() -> None:
    print("Downloading SpeechBrain ECAPA speaker encoder…")
    from speechbrain.inference.speaker import EncoderClassifier

    EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(Path.home() / ".cache" / "speechbrain" / "spkrec-ecapa-voxceleb"),
        run_opts={"device": "cpu"},
    )
    print("✓ Speaker encoder cached")


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 50)
    print("Marvin Model Downloader")
    print("=" * 50)
    print()
    print("Models to download:")
    print("  • Silero VAD")
    print("  • Whisper large-v3-turbo (int8)")
    print("  • Qwen3 4B Instruct Q4_K_M")
    print("  • Kokoro-82M TTS")
    print("  • SpeechBrain ECAPA speaker encoder")
    print()

    steps = [
        ("Silero VAD", download_silero_vad),
        ("Whisper", download_whisper),
        ("Qwen3 4B", download_llm),
        ("Kokoro", download_kokoro),
        ("Speaker encoder", download_speaker),
    ]
    for name, fn in steps:
        try:
            fn()
        except Exception as exc:
            print(f"✗ Failed to download {name}: {exc}", file=sys.stderr)
            sys.exit(1)

    print()
    print("All models downloaded successfully!")
    print(f"Models stored in: {MODELS_DIR}")


if __name__ == "__main__":
    main()
