"""test_ai_synthesis.py — Offline tests for the Gemini lens layer.

No network, no google-genai required: covers the output validator (P1-023)
and prompt hygiene (P1-021/P1-022 — no invented credentials, no trade
directives, mandatory evidence/falsification ground rules).
"""
from __future__ import annotations
import os, re, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_synthesis
from ai_synthesis import _validate_persona, _AGENTS, _LENS_GROUND_RULES


def _good(**over) -> dict:
    base = {
        "stance": "Cautious",
        "stance_color": "yellow",
        "read": "Trend fields are positive but breadth is narrow.",
        "points": [{"icon": "⚠️", "text": "RSP lags SPY by 0.4% — index strength is narrow."}],
        "verdict": "Constructive structure, uneven participation.",
    }
    base.update(over)
    return base


class TestValidatePersona(unittest.TestCase):

    def test_valid_output_passes_and_is_normalized(self):
        clean = _validate_persona(_good(stance="cautious"))
        self.assertEqual(clean["stance"], "Cautious")

    def test_stance_color_is_derived_never_trusted(self):
        clean = _validate_persona(_good(stance="Bearish", stance_color="green"))
        self.assertEqual(clean["stance_color"], "red")

    def test_unknown_stance_rejected(self):
        self.assertIsNone(_validate_persona(_good(stance="Euphoric")))

    def test_missing_keys_rejected(self):
        bad = _good()
        del bad["verdict"]
        self.assertIsNone(_validate_persona(bad))

    def test_non_dict_and_empty_points_rejected(self):
        self.assertIsNone(_validate_persona("nope"))
        self.assertIsNone(_validate_persona(_good(points=[])))
        self.assertIsNone(_validate_persona(_good(points="not a list")))
        self.assertIsNone(_validate_persona(_good(points=[{"icon": "x", "text": ""}])))

    def test_lengths_and_point_count_clamped(self):
        clean = _validate_persona(_good(
            read="r" * 5000,
            verdict="v" * 5000,
            points=[{"icon": "✅", "text": "t" * 5000}] * 12,
        ))
        self.assertLessEqual(len(clean["read"]), ai_synthesis._MAX_READ_CHARS)
        self.assertLessEqual(len(clean["verdict"]), ai_synthesis._MAX_VERDICT_CHARS)
        self.assertLessEqual(len(clean["points"]), ai_synthesis._MAX_POINTS)
        for pt in clean["points"]:
            self.assertLessEqual(len(pt["text"]), ai_synthesis._MAX_POINT_CHARS)


class TestPromptHygiene(unittest.TestCase):
    """P1-021/P1-022: the system prompts themselves must not manufacture
    authority or demand trade directives."""

    _BANNED = re.compile(
        r"prop trading firm|\d+ years|best analysts|zero hedging"
        r"|exact size|stop level|entry trigger|SIZE and .*STOPS"
        r"|ONE sector to BUY|position size recommendation",
        re.IGNORECASE)

    def test_no_credentials_or_directives_in_prompts(self):
        for agent in _AGENTS:
            with self.subTest(agent=agent["persona"]):
                m = self._BANNED.search(agent["system"])
                self.assertIsNone(m, f"{agent['persona']} prompt contains {m.group(0)!r}" if m else None)

    def test_every_lens_carries_the_ground_rules(self):
        for agent in _AGENTS:
            with self.subTest(agent=agent["persona"]):
                self.assertIn(_LENS_GROUND_RULES, agent["system"])

    def test_ground_rules_demand_falsification_and_forbid_directives(self):
        self.assertIn("falsify", _LENS_GROUND_RULES)
        self.assertIn("NEVER give trade instructions", _LENS_GROUND_RULES)
        self.assertIn("not independent confirmation", _LENS_GROUND_RULES)


if __name__ == "__main__":
    unittest.main()
