"""Multi-tool turn composition and force-until-families tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.tools.multi_tool import (
    collect_required_families,
    compose_prompt_blurb,
    compose_tools,
    families_satisfied,
    family_for_tool_name,
    prefixes_for_families,
    primary_family,
    tool_result_is_success,
)
from backend.pipeline.llm import QwenLLM


class MultiToolComposeTests(unittest.TestCase):
    def test_collect_spotify_and_scrambler(self):
        families = collect_required_families(
            spotify_required=True,
            scrambler_needed=True,
            timer_needed=False,
            switch_needed=False,
            python_needed=False,
        )
        self.assertEqual(families, ["spotify", "scrambler"])
        self.assertEqual(primary_family(families), "spotify")
        prefixes = prefixes_for_families(families)
        self.assertIn("spotify", prefixes)
        self.assertIn("scrambler_", prefixes)

    def test_compose_tools_merges_schemas(self):
        families = ["spotify", "scrambler"]
        tools = compose_tools(
            families,
            providers={
                "spotify": lambda: [
                    {"type": "function", "function": {"name": "spotify_play"}}
                ],
                "scrambler": lambda: [
                    {"type": "function", "function": {"name": "scrambler_start"}}
                ],
            },
        )
        names = [t["function"]["name"] for t in tools]
        self.assertEqual(names, ["spotify_play", "scrambler_start"])

    def test_compose_prompt_mentions_multiple(self):
        blurb = compose_prompt_blurb(["spotify", "scrambler"])
        self.assertIn("multiple tools", blurb.lower())
        self.assertIn("Spotify", blurb)
        self.assertIn("scrambler", blurb.lower())

    def test_family_mapping_and_success(self):
        self.assertEqual(family_for_tool_name("spotify_play"), "spotify")
        self.assertEqual(family_for_tool_name("scrambler_start"), "scrambler")
        self.assertEqual(family_for_tool_name("timer_start"), "timers")
        self.assertTrue(
            tool_result_is_success(
                "scrambler_start", "Voice scrambler started → output “BlackHole”."
            )
        )
        self.assertFalse(tool_result_is_success("spotify_play", "Error: no device"))
        self.assertTrue(families_satisfied(["spotify", "scrambler"], ["spotify", "scrambler"]))
        self.assertFalse(families_satisfied(["spotify", "scrambler"], ["spotify"]))


class ForceUntilFamiliesTests(unittest.TestCase):
    def test_force_continues_until_all_families_hit(self):
        llm = object.__new__(QwenLLM)
        llm._history = []
        llm._cancel_event = None
        calls = {"n": 0}
        executed: list[str] = []

        def execute(name, args, user_message):
            executed.append(name)
            if name == "spotify_play":
                return "Playing Radiohead."
            if name == "scrambler_start":
                return "Voice scrambler started → output BlackHole."
            return "ok"

        def sequenced(**kwargs):
            calls["n"] += 1
            n = calls["n"]
            if n == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "1",
                                        "function": {
                                            "name": "spotify_play",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            if n == 2:
                # Early answer — nudge because scrambler family still missing.
                return {
                    "choices": [{"message": {"content": "Playing Radiohead."}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            if n == 3:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "2",
                                        "function": {
                                            "name": "scrambler_start",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Playing Radiohead and scrambling your voice."
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        llm._create_chat_completion = sequenced
        llm._log_model_call = lambda *a, **k: (1, 1, 0.01)
        llm._extract_text_tool_calls = lambda _c: []
        llm._finalize_reply = lambda text: text
        llm._explicitly_references_history = lambda _m: False

        tools = [
            {"type": "function", "function": {"name": "spotify_play"}},
            {"type": "function", "function": {"name": "scrambler_start"}},
        ]
        reply = llm.chat_with_tools(
            "play radiohead on spotify and scramble voice",
            "System",
            tools,
            execute,
            force_tool_use=True,
            required_tool_prefixes=["spotify", "scrambler_"],
        )
        self.assertIn("spotify_play", executed)
        self.assertIn("scrambler_start", executed)
        self.assertIn("scrambling", reply.lower())
        metrics = llm.last_metrics
        self.assertTrue(metrics.get("successful_side_effects"))
        self.assertIn("spotify", metrics.get("hit_families") or [])
        self.assertIn("scrambler", metrics.get("hit_families") or [])


class AgentMultiToolPathTests(unittest.TestCase):
    def test_spotify_plus_scrambler_runs_both(self):
        from backend.agent import MarvinAgent
        from backend.tools.spotify.routing import SpotifyDecision

        agent = MarvinAgent()
        agent._llm = MagicMock()
        agent._llm.last_metrics = {
            "tool_calls": 1,
            "successful_side_effects": True,
            "hit_families": ["spotify", "scrambler"],
        }
        agent._llm.chat_with_tools.return_value = (
            "Playing Radiohead and scrambling your voice."
        )
        agent._llm.remember_exchange = MagicMock()
        agent._llm.active_selection = ("local", "qwen")
        agent._spotify_tool_texts = []

        executed: list[str] = []

        def fake_direct(text):
            executed.append("scrambler_direct")
            return "Voice scrambler started → output BlackHole."

        with (
            patch(
                "backend.tools.obsidian.register_vault_capability",
                return_value=False,
            ),
            patch(
                "backend.tools.web_search.service.register_web_search_capability",
                return_value=False,
            ),
            patch(
                "backend.tools.spotify.register_spotify_capability",
                return_value=True,
            ),
            patch(
                "backend.tools.python_runner.register_python_capability",
                return_value=False,
            ),
            patch(
                "backend.tools.timers.register_timer_capability",
                return_value=True,
            ),
            patch(
                "backend.tools.spotify.decide_spotify",
                return_value=(SpotifyDecision.REQUIRED, "play"),
            ),
            patch(
                "backend.tools.web_search.routing.decide_web_search",
                return_value=(
                    __import__(
                        "backend.tools.web_search.types", fromlist=["SearchDecision"]
                    ).SearchDecision.NOT_NEEDED,
                    "none",
                ),
            ),
            patch(
                "backend.tools.python_runner.decide_python",
                return_value=False,
            ),
            patch("backend.tools.timers.decide_timer", return_value=False),
            patch("backend.tools.ai_model.decide_switch_model", return_value=False),
            patch(
                "backend.tools.voice_scrambler.decide_scrambler",
                return_value=True,
            ),
            patch(
                "backend.tools.voice_scrambler.handle_direct_scrambler",
                side_effect=fake_direct,
            ),
            patch(
                "backend.tools.obsidian.explicit_vault_intent",
                return_value=False,
            ),
            patch(
                "backend.tools.obsidian.extract_named_note_hint",
                return_value=None,
            ),
            patch.object(agent, "_route_function", return_value=("chat", "fast")),
            patch.object(agent, "_maybe_auto_continue_spotify", side_effect=lambda *a, **k: (a[1], False)),
            patch.object(agent, "begin_tool", return_value="t1"),
            patch.object(agent, "finish_tool"),
        ):
            reply, routed, side = agent._process_text_once(
                "play radiohead on spotify and scramble voice",
                show_user=False,
            )

        self.assertIn("scrambler_direct", executed)
        self.assertTrue(agent._llm.chat_with_tools.called)
        kwargs = agent._llm.chat_with_tools.call_args.kwargs
        self.assertIn("spotify", kwargs.get("required_tool_prefixes") or [])
        # Scrambler already direct-satisfied — not required of the LLM.
        self.assertNotIn("scrambler_", kwargs.get("required_tool_prefixes") or [])
        self.assertEqual(kwargs.get("pre_satisfied_families"), ["scrambler"])
        self.assertEqual(routed, "spotify")
        self.assertTrue(side)
        self.assertIn("Radiohead", reply)


if __name__ == "__main__":
    unittest.main()
