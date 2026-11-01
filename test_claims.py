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
    "data.py",
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
    # Sizing and exposure instructions
    r"half[- ]size",
    r"half size",
    r"size down",
    r"small size",
    r"standard size",
    r"(cut|reduce|trim) (size|exposure|position|gross|intraweek|duration)",
    r"reduce position",
    r"trade small",
    r"full exposure",
    r"(standard|moderate|reduced) exposure",
    r"defensive / flat",
    r"exposure off",
    r"cash is a position",
    r"protect your capital",
    r"capital preservation",
    # Stops and protection
    r"(tight|tighter|tighten|wide|widen|standard) stops",
    r"hedge cheap",
    r"carry protection",
    r"cheap protection",
    r"cheap to hedge",
    # Entry, exit and timing instructions
    r"stand aside",
    r"sit (on hands|out)",
    r"no new longs",
    r"don'?t (chase|add|hold)",
    r"wait for (a |an |the )?(first |intraday )?(pullback|reclaim|reset|cash)",
    r"before (adding|entry|chasing|probing)",
    r"hold off",
    r"probing longs",
    r"(entry|re-entry) zone",
    r"mediocre entries",
    r"planning the exit",
    r"for offense",
    r"the play\b",
    r"be patient",
    r"selective longs",
    r"(trade|trading) (the trend|what|shorter)",
    r"a\+ (setups?|trade|pullbacks?)",
    r"setups only",
    r"veto a good setup",
    r"quick in",
    r"let it settle",
    r"bear-market rules",
    r"defined[- ]risk",
    # Labels that imply a timing or trading style the evidence doesn't support
    r"drawdown-timed",
    r"swing trading",
    r"quality terminal",
    # Execution Window rows, which failed backtest_execution_window.py
    r"breakouts working",
    r"leaders holding",
    r"pullbacks bought",
    # Direction and selection instructions
    r"contrarian long",
    r"avoid or short",
    r"hunt (here|list|for)",
    r"shopping list",
    r"rotate into",
    r"only trade",
    r"stay out of",
    r"follow the (money|rs)",
    r"follow, don'?t predict",
    r"fade-the-last-buyer",
    r"reach (further )?out the risk curve",
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

    def test_rendered_personas_issue_no_instructions(self):
        """Render every lens across calm, mixed and stressed markets, so copy
        assembled at runtime is checked as well as the source text."""
        import analysis
        pattern = re.compile("|".join(f"(?:{p})" for p in PROHIBITED), re.IGNORECASE)

        def dash(score, vix, above, vix9d, skew, rsi, fomc, spy_chg, participation):
            return {
                "total_score": score, "decision": "SELECTIVE", "position_size": "MIXED CONDITIONS",
                "conflicts": [],
                "pillars": {
                    "trend": {"score": score, "details": {
                        "above_20": above, "above_50": above, "above_200": above, "ath_dist": -12 if not above else -0.5,
                        "rsi14": rsi, "spy_change_pct": spy_chg, "macd_hist": 0.1,
                        "macd_label": "Bearish (below 0)" if not above else "Bullish (above 0)",
                        "char_label": "Trending", "regime": "Mixed"}},
                    "macro": {"score": score, "details": {
                        "tnx_value": 4.7, "yield_direction": "Rising", "dxy_label": "Strengthening",
                        "dxy_change_pct": 0.5, "btc_trend": "Mixed", "fomc_days": fomc, "fomc_date": "Dec 09"}},
                    "volatility": {"score": score, "details": {
                        "vix_level": vix, "vix_label": "x", "vix_trend": "Spiking", "vix_pctile": 85,
                        "flow_score": 90 if above else 10, "flow_label": "x", "vix9d_ratio": 1.2, "vix9d_label": vix9d,
                        "skew_value": 150, "skew_label": skew}},
                    "breadth": {"score": score, "details": {"rsp_vs_spy": -0.5, "sectors_positive": 3, "sectors_total": 11}},
                    "momentum": {"score": score, "details": {
                        "participation": participation, "sectors_positive": 3, "sectors_total": 11, "growth_leaders": 2,
                        "rsp_vs_spy": -0.5, "iwm_vs_spy": 0.5,
                        "leader": {"name": "Energy", "change_pct": 1}, "laggard": {"name": "Tech", "change_pct": -1},
                        "sector_rs": [{"name": "Energy", "rs_score": 2.0}, {"name": "Tech", "rs_score": -2.0}]}},
                },
            }

        scenarios = [
            dash(90, 12, True, "Calm", "Complacent", 76, None, 2.0, "Broad"),
            dash(60, 18, True, "Fear Spike", "Elevated Hedging", 50, 5, 0.1, "Mixed"),
            dash(45, 26, False, "Fear Spike", "Elevated Hedging", 65, 2, -2.0, "Narrow"),
            dash(20, 35, False, "Normal", "Normal", 25, 0, -2.0, "Narrow"),
        ]
        offenders = []
        for d in scenarios:
            for persona in analysis.roundtable(d)["personas"]:
                texts = [persona["read"], persona["verdict"]] + [p["text"] for p in persona["points"]]
                offenders += [f"{persona['persona']}: {t}" for t in texts if pattern.search(t)]
        self.assertEqual(offenders, [], "\n".join(offenders))

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
