"""test_claims.py — Claim-hygiene guard (P0-009, decision D-001).

The 2005–2026 replay (docs/backtest-report.md) found no return-timing edge,
so user-facing copy must describe conditions — it must not issue trade
instructions or authority language. This suite fails CI if prohibited
phrases reappear in shipped product copy.

Scope: product source files only. Docs, tests, and the historical
backtest/QC scripts are exempt (they may quote or discuss the old copy).
"""
from __future__ import annotations
import os, re, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))

# User-facing product copy lives in these files.
PRODUCT_FILES = [
    "scoring.py",
    "analysis.py",
    "ai_synthesis.py",
    "notify.py",
    "watchlist.py",
    "static/app.js",
    "static/classic.js",
    "should-i-trade-v6.html",
    "classic.html",
]

# Directive/authority phrases the evidence does not support (D-001).
# (The '{skew_label}' literal-placeholder bug class is covered at runtime by
# test_analysis.py, which asserts rendered persona text — a source-level scan
# would false-positive on legitimate f-strings.)
PROHIBITED = [
    r"press (the )?bid",
    r"press size",
    r"green light",
    r"full size",
    # P1-021: manufactured authority in AI prompts or product copy
    r"prop trading firm",
    r"zero hedging",
    r"best analysts",
    r"years running trading desks",
    r"\d+ years reading charts",
]


class TestClaimHygiene(unittest.TestCase):

    def test_no_prohibited_phrases_in_product_copy(self):
        pattern = re.compile("|".join(f"(?:{p})" for p in PROHIBITED), re.IGNORECASE)
        offenders = []
        for rel in PRODUCT_FILES:
            path = os.path.join(HERE, rel)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    m = pattern.search(line)
                    if m:
                        offenders.append(f"{rel}:{lineno}: {m.group(0)!r}")
        self.assertEqual(offenders, [],
                         "Prohibited directive copy found (see docs/project-improvement-plan.md D-001):\n"
                         + "\n".join(offenders))

    def test_decision_band_actions_are_descriptive(self):
        """Band actions must not contain exposure/entry verbs."""
        import scoring
        directive = re.compile(
            r"press|chase|add on|entry|entries|stops?\b|sit out|no new longs|exposure —",
            re.IGNORECASE)
        for band in scoring.DECISION_BANDS:
            with self.subTest(band=band["decision"]):
                self.assertIsNone(directive.search(band["action"]),
                                  f"{band['decision']} action is directive: {band['action']!r}")


if __name__ == "__main__":
    unittest.main()
