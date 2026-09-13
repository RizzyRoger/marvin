"""Speech list summarization and Output Speech prefs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.pipeline.speech_summary import summarize_for_speech
from backend import speech_settings as ss


class SpeechSummaryTests(unittest.TestCase):
    def test_collapses_long_markdown_list(self):
        text = "Here are the top 10 Radiohead songs:\n" + "\n".join(
            f"{i}. Song {i}" for i in range(1, 11)
        )
        spoken = summarize_for_speech(text)
        self.assertNotIn("Song 5", spoken)
        self.assertTrue(
            "top 10" in spoken.lower() or "10 items" in spoken.lower() or "here" in spoken.lower()
        )

    def test_keeps_short_replies(self):
        text = "Playing Karma Police by Radiohead."
        self.assertEqual(summarize_for_speech(text), text)


class SpeechSettingsTests(unittest.TestCase):
    def test_save_and_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Path(tmp) / "speech_prefs.json"
            with patch.object(ss, "_PREFS_PATH", prefs):
                saved = ss.save_speech_settings(
                    nationality="american", gender="female", mode="voice_input_only"
                )
                self.assertEqual(saved.nationality, "american")
                self.assertEqual(saved.gender, "female")
                self.assertEqual(saved.mode, "voice_input_only")
                loaded = ss.load_speech_settings()
                self.assertEqual(loaded.mode, "voice_input_only")
                preferred_id, _onnx, _cfg = ss.preferred_piper_paths(loaded)
                self.assertEqual(preferred_id, "en_US-lessac-medium")


if __name__ == "__main__":
    unittest.main()
