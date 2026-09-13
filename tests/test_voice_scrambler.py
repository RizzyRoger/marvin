"""Tests for five-strand scrambler DSP and device preference."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from backend.tools.voice_scrambler import dsp
from backend.tools import voice_scrambler as vs


class ScramblerDspTests(unittest.TestCase):
    def test_clarity_disguise_interpolates(self):
        clear = dsp.interpolate_strand_params(0.0)
        disguise = dsp.interpolate_strand_params(1.0)
        mid = dsp.interpolate_strand_params(0.5)
        self.assertEqual(clear["pitch"][0], -3.0)
        self.assertEqual(disguise["pitch"][0], -7.0)
        self.assertAlmostEqual(mid["pitch"][0], -5.0)
        self.assertLess(disguise["gain"][2], clear["gain"][2])

    def test_processor_preserves_length(self):
        proc = dsp.FiveStrandProcessor(sample_rate=16000)
        block = np.random.default_rng(0).normal(0, 0.1, size=256).astype(np.float32)
        out = proc.process(block)
        self.assertEqual(out.shape, block.shape)
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)


class VoiceScramblerTests(unittest.TestCase):
    def tearDown(self) -> None:
        vs.shutdown_scrambler()

    def test_decide_scrambler_phrases(self):
        self.assertTrue(vs.decide_scrambler("scramble my voice"))
        self.assertTrue(vs.decide_scrambler("start the voice scrambler"))
        self.assertTrue(vs.decide_scrambler("anonymous mic for zoom"))
        self.assertFalse(vs.decide_scrambler("play some music"))
        self.assertFalse(vs.decide_scrambler("", available=True))
        self.assertFalse(vs.decide_scrambler("scramble my voice", available=False))

    def test_handle_direct_scrambler_start_stop(self):
        with patch.object(vs, "start_scrambler", return_value="started ok") as start:
            self.assertEqual(vs.handle_direct_scrambler("scramble my voice"), "started ok")
            start.assert_called_once()
        with patch.object(vs, "stop_scrambler", return_value="stopped ok") as stop:
            self.assertEqual(
                vs.handle_direct_scrambler("stop the voice scrambler"),
                "stopped ok",
            )
            stop.assert_called_once()
        self.assertIsNone(vs.handle_direct_scrambler("what's the weather"))

    def test_start_stop_status_mocked(self):
        fake_engine = MagicMock()
        fake_engine.running = True
        fake_engine.output_device = 3
        fake_engine.output_name = "BlackHole 2ch"
        fake_engine._error = None

        with (
            patch.object(vs, "_resolve_output_device", return_value=(3, "BlackHole 2ch")),
            patch.object(vs, "ScramblerEngine", return_value=fake_engine) as engine_cls,
            patch.object(
                vs,
                "list_output_devices",
                return_value=[
                    {"index": 3, "name": "BlackHole 2ch", "kind": "virtual"}
                ],
            ),
            patch.object(vs, "_save_prefs"),
            patch.object(vs, "_load_prefs", return_value={}),
        ):
            started = vs.start_scrambler("BlackHole")
            self.assertIn("started", started.lower())
            self.assertEqual(engine_cls.call_args.args[:2], (3, "BlackHole 2ch"))
            fake_engine.start.assert_called_once()

            status = vs.scrambler_status_payload()
            self.assertTrue(status["running"])
            self.assertEqual(status["output_device"], "BlackHole 2ch")

            stopped = vs.stop_scrambler()
            self.assertIn("stopped", stopped.lower())
            fake_engine.stop.assert_called()

    def test_refuse_speaker_output(self):
        with patch.object(
            vs, "_resolve_output_device", return_value=(1, "MacBook Pro Speakers")
        ):
            msg = vs.start_scrambler("Speakers")
            self.assertIn("Refusing", msg)

    def test_prefer_virtual_device(self):
        devices = [
            {
                "index": 0,
                "name": "MacBook Speakers",
                "channels": 2,
                "default": True,
                "kind": "speaker",
            },
            {
                "index": 2,
                "name": "BlackHole 2ch",
                "channels": 2,
                "default": False,
                "kind": "virtual",
            },
        ]
        with (
            patch.object(vs, "list_output_devices", return_value=devices),
            patch.object(vs, "_load_prefs", return_value={}),
        ):
            idx, name = vs._resolve_output_device(None)
            self.assertEqual(idx, 2)
            self.assertIn("BlackHole", name)

    def test_dispatch_tools(self):
        with patch.object(vs, "start_scrambler", return_value="ok start") as start:
            self.assertEqual(
                vs.dispatch_scrambler_tool(
                    "scrambler_start", {"output_device": "BH"}, "start scrambler"
                ),
                "ok start",
            )
            start.assert_called_once_with("BH")
        with patch.object(vs, "stop_scrambler", return_value="ok stop"):
            self.assertEqual(
                vs.dispatch_scrambler_tool("scrambler_stop", {}, "stop"),
                "ok stop",
            )
        with patch.object(
            vs, "scrambler_status_payload", return_value={"running": False}
        ):
            out = vs.dispatch_scrambler_tool("scrambler_status", {}, "status")
            self.assertIn("stopped", out.lower())


if __name__ == "__main__":
    unittest.main()
