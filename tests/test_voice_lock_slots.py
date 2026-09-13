"""Voice Lock 7.30 enrollment slot shape without loading SpeechBrain."""

from __future__ import annotations

import unittest

from backend.config import (
    ENROLL_NATURAL_PROMPT,
    SPEAKER_ENROLL_COUNT,
    enrollment_phrases,
)
from backend.pipeline.speaker import SpeakerVerifier


class EnrollmentSlotTests(unittest.TestCase):
    def test_six_phrases_include_one_natural_prompt(self):
        phrases = enrollment_phrases()
        self.assertEqual(len(phrases), SPEAKER_ENROLL_COUNT)
        self.assertEqual(SPEAKER_ENROLL_COUNT, 6)
        self.assertEqual(phrases.count(ENROLL_NATURAL_PROMPT), 1)

    def test_slots_expose_sample_ids_and_natural_type(self):
        verifier = object.__new__(SpeakerVerifier)
        verifier._samples = []
        phrases = enrollment_phrases()
        payload = SpeakerVerifier.ensure_enrollment_slots(verifier, phrases)
        self.assertEqual(len(payload), 6)
        self.assertTrue(all(item.get("sample_id") for item in payload))
        natural = [item for item in payload if item["prompt_type"] == "natural"]
        self.assertEqual(len(natural), 1)
        self.assertEqual(natural[0]["prompt_text"], ENROLL_NATURAL_PROMPT)
        self.assertEqual(natural[0]["status"], "not_recorded")

    def test_reset_sample_clears_one_slot(self):
        verifier = object.__new__(SpeakerVerifier)
        verifier._samples = []
        SpeakerVerifier.ensure_enrollment_slots(verifier, enrollment_phrases())
        sample_id = verifier._samples[0]["sample_id"]
        verifier._samples[0]["status"] = "accepted"
        verifier._samples[0]["embedding"] = object()
        result = SpeakerVerifier.reset_enrollment_sample(verifier, sample_id)
        self.assertEqual(result["sample_id"], sample_id)
        self.assertEqual(verifier._samples[0]["status"], "not_recorded")
        self.assertIsNone(verifier._samples[0]["embedding"])
