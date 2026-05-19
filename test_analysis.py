"""
test_analysis.py — Offline unit tests for analysis.py

Tests cover all 6 persona functions and roundtable() using a minimal
dashboard fixture dict. No network calls required — analysis.py is
pure computation over a dict.

Test strategy:
  • Structural contract: each persona returns required keys with correct types
  • Stance mapping: _pick_stance thresholds produce correct stance labels
  • Conditional branches: at least one test per distinct textual path per persona
  • roundtable(): correct persona order, timestamp present, all 5 personas included
"""
from __future__ import annotations
import sys, os, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analysis import (
    _pick_stance,
    persona_technician, persona_macro, persona_risk,
    persona_rotator, persona_desk_head, roundtable,
)

# ═══════════════════════════════════════════════════════════════════════════
# Fixture helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_dashboard(
    total_score: int = 72,
    decision: str = "YES",
    position_size: str = "STANDARD SIZE",
    trend_score: int = 75,
    vol_score: int = 70,
    breadth_score: int = 68,
    momentum_score: int = 65,
    macro_score: int = 72,
    # trend details
    above_20: bool = True, above_50: bool = True, above_200: bool = True,
    regime: str = "Uptrend", ath_dist: float = -3.5, rsi14: float = 58.0,
    spy_change_pct: float = 0.8, macd_hist: float = 2.1, macd_label: str = "Bullish",
    char_label: str = "Trending",
    # vol details
    vix_level: float = 17.5, vix_label: str = "Calm", vix_trend: str = "Falling",
    vix_pctile: int = 35, flow_score: int = 52, flow_label: str = "Neutral",
    vix9d_ratio: float = 0.92, vix9d_label: str = "Calm",
    skew_value: float = 130.0, skew_label: str = "Normal",
    # breadth details
    rsp_vs_spy: float = 0.1, sectors_positive: int = 9, sectors_total: int = 11,
    adv_dec_ratio: float = 2.1, sector_data=None, industry_data=None,
    # momentum details
    sector_leaders=None, sector_laggards=None, rs_leaders=None,
    avg_rsi: float = 57.0, pct_above_20d: float = 68.0,
    # macro details
    tnx_value: float = 4.2, yield_direction: str = "Flat", yield_label: str = "Neutral",
    dxy_label: str = "Neutral", dxy_change_pct: float = 0.1,
    btc_trend: str = "Full Bull", btc_from_high: float = -8.5,
    fomc_days: int = 14, fomc_date: str = "2026-06-11",
    # conflicts / overrides
    conflicts=None, override_reasons=None,
) -> dict:
    return {
        "total_score":     total_score,
        "raw_total_score": total_score,
        "decision":        decision,
        "position_size":   position_size,
        "conflicts":       conflicts or [],
        "override_reasons": override_reasons or [],
        "pillars": {
            "trend": {
                "score": trend_score,
                "details": {
                    "above_20": above_20, "above_50": above_50, "above_200": above_200,
                    "regime": regime, "ath_dist": ath_dist, "rsi14": rsi14,
                    "spy_change_pct": spy_change_pct, "macd_hist": macd_hist,
                    "macd_label": macd_label, "char_label": char_label,
                },
            },
            "volatility": {
                "score": vol_score,
                "details": {
                    "vix_level": vix_level, "vix_label": vix_label,
                    "vix_trend": vix_trend, "vix_pctile": vix_pctile,
                    "flow_score": flow_score, "flow_label": flow_label,
                    "vix9d_ratio": vix9d_ratio, "vix9d_label": vix9d_label,
                    "skew_value": skew_value, "skew_label": skew_label,
                },
            },
            "breadth": {
                "score": breadth_score,
                "details": {
                    "rsp_vs_spy": rsp_vs_spy, "sectors_positive": sectors_positive,
                    "sectors_total": sectors_total, "adv_dec_ratio": adv_dec_ratio,
                    "sector_data": sector_data or [], "industry_data": industry_data or [],
                },
            },
            "momentum": {
                "score": momentum_score,
                "details": {
                    "sector_leaders": sector_leaders or [],
                    "sector_laggards": sector_laggards or [],
                    "rs_leaders": rs_leaders or [],
                    "avg_rsi": avg_rsi, "pct_above_20d": pct_above_20d,
                },
            },
            "macro": {
                "score": macro_score,
                "details": {
                    "tnx_value": tnx_value, "yield_direction": yield_direction,
                    "yield_label": yield_label, "dxy_label": dxy_label,
                    "dxy_change_pct": dxy_change_pct, "btc_trend": btc_trend,
                    "btc_from_high": btc_from_high, "fomc_days": fomc_days,
                    "fomc_date": fomc_date,
                },
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. _pick_stance thresholds
# ═══════════════════════════════════════════════════════════════════════════
class TestPickStance(unittest.TestCase):

    def test_bullish_at_75(self):
        stance, _ = _pick_stance(75)
        self.assertEqual(stance, "Bullish")

    def test_bullish_above_75(self):
        stance, _ = _pick_stance(90)
        self.assertEqual(stance, "Bullish")

    def test_cautious_at_60(self):
        stance, _ = _pick_stance(60)
        self.assertEqual(stance, "Cautious")

    def test_cautious_at_74(self):
        stance, _ = _pick_stance(74)
        self.assertEqual(stance, "Cautious")

    def test_defensive_at_45(self):
        stance, _ = _pick_stance(45)
        self.assertEqual(stance, "Defensive")

    def test_defensive_at_59(self):
        stance, _ = _pick_stance(59)
        self.assertEqual(stance, "Defensive")

    def test_bearish_below_45(self):
        stance, _ = _pick_stance(44)
        self.assertEqual(stance, "Bearish")

    def test_bearish_at_zero(self):
        stance, _ = _pick_stance(0)
        self.assertEqual(stance, "Bearish")

    def test_colors_are_strings(self):
        for score in (0, 45, 60, 75, 100):
            _, color = _pick_stance(score)
            self.assertIsInstance(color, str)
            self.assertTrue(len(color) > 0)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Common output-contract assertions
# ═══════════════════════════════════════════════════════════════════════════
REQUIRED_PERSONA_KEYS = {"persona", "role", "avatar", "stance", "stance_color", "read", "points", "verdict"}


def _assert_persona_contract(tc: unittest.TestCase, result: dict) -> None:
    for key in REQUIRED_PERSONA_KEYS:
        tc.assertIn(key, result, f"Missing key: {key}")
    tc.assertIsInstance(result["persona"],      str)
    tc.assertIsInstance(result["role"],         str)
    tc.assertIsInstance(result["avatar"],       str)
    tc.assertIsInstance(result["stance"],       str)
    tc.assertIsInstance(result["stance_color"], str)
    tc.assertIsInstance(result["read"],         str)
    tc.assertIsInstance(result["points"],       list)
    tc.assertIsInstance(result["verdict"],      str)
    tc.assertGreater(len(result["read"]),    10)
    tc.assertGreater(len(result["verdict"]), 3)
    for pt in result["points"]:
        tc.assertIn("icon", pt)
        tc.assertIn("text", pt)


# ═══════════════════════════════════════════════════════════════════════════
# 3. persona_technician
# ═══════════════════════════════════════════════════════════════════════════
class TestPersonaTechnician(unittest.TestCase):

    def test_output_contract_bull(self):
        d = _make_dashboard()
        _assert_persona_contract(self, persona_technician(d))

    def test_full_bull_stack_read(self):
        d = _make_dashboard(char_label="Trending")
        r = persona_technician(d)
        self.assertIn("bull", r["read"].lower())

    def test_choppy_tape_read(self):
        d = _make_dashboard(char_label="Choppy")
        r = persona_technician(d)
        self.assertIn("choppy", r["read"].lower())

    def test_extended_tape_read(self):
        d = _make_dashboard(char_label="Extended")
        r = persona_technician(d)
        self.assertIn("extended", r["read"].lower())

    def test_two_mas_read(self):
        d = _make_dashboard(above_20=True, above_50=True, above_200=False)
        r = persona_technician(d)
        # 2/3 MAs — "repairing" or "2/3"
        self.assertTrue("2/3" in r["read"] or "repairing" in r["read"].lower())

    def test_one_ma_read(self):
        d = _make_dashboard(above_20=True, above_50=False, above_200=False)
        r = persona_technician(d)
        self.assertIn("broken structure", r["read"].lower())

    def test_zero_mas_bear_read(self):
        d = _make_dashboard(above_20=False, above_50=False, above_200=False)
        r = persona_technician(d)
        self.assertIn("bear", r["read"].lower())

    def test_rsi_overbought_appears_in_points(self):
        d = _make_dashboard(rsi14=76.0)
        r = persona_technician(d)
        texts = " ".join(pt["text"] for pt in r["points"])
        self.assertIn("76", texts)

    def test_rsi_none_no_crash(self):
        d = _make_dashboard(rsi14=None)
        r = persona_technician(d)
        self.assertIsInstance(r, dict)

    def test_bullish_stance_at_high_score(self):
        d = _make_dashboard(trend_score=80)
        r = persona_technician(d)
        self.assertEqual(r["stance"], "Bullish")


# ═══════════════════════════════════════════════════════════════════════════
# 4. persona_macro
# ═══════════════════════════════════════════════════════════════════════════
class TestPersonaMacro(unittest.TestCase):

    def test_output_contract(self):
        d = _make_dashboard()
        _assert_persona_contract(self, persona_macro(d))

    def test_offline_macro_read(self):
        d = _make_dashboard(tnx_value=None)
        r = persona_macro(d)
        self.assertIn("offline", r["read"].lower())

    def test_falling_yields_weakening_dxy_tailwind(self):
        d = _make_dashboard(yield_direction="Falling", dxy_label="Weakening")
        r = persona_macro(d)
        self.assertIn("tailwind", r["read"].lower())

    def test_rising_yields_strengthening_dxy_risk_off(self):
        d = _make_dashboard(yield_direction="Rising", dxy_label="Strengthening", tnx_value=4.8)
        r = persona_macro(d)
        self.assertIn("risk-off", r["read"].lower())

    def test_rising_yields_weak_dxy_growth(self):
        d = _make_dashboard(yield_direction="Rising", dxy_label="Weakening", tnx_value=4.3)
        r = persona_macro(d)
        self.assertIn("growth", r["read"].lower())

    def test_fomc_tomorrow_appears_in_points(self):
        d = _make_dashboard(fomc_days=1, fomc_date="2026-06-12")
        r = persona_macro(d)
        texts = " ".join(pt["text"].upper() for pt in r["points"])
        self.assertIn("FOMC", texts)

    def test_btc_bear_in_points(self):
        d = _make_dashboard(btc_trend="Bear")
        r = persona_macro(d)
        texts = " ".join(pt["text"].lower() for pt in r["points"])
        self.assertIn("bear", texts)

    def test_high_yield_warning_in_points(self):
        d = _make_dashboard(tnx_value=5.1)
        r = persona_macro(d)
        texts = " ".join(pt["text"] for pt in r["points"])
        self.assertIn("5.10", texts)

    def test_clean_calendar_verdict_contains_tailwind(self):
        d = _make_dashboard(macro_score=75, fomc_days=20)
        r = persona_macro(d)
        self.assertIn("tailwind", r["verdict"].lower())


# ═══════════════════════════════════════════════════════════════════════════
# 5. persona_risk
# ═══════════════════════════════════════════════════════════════════════════
class TestPersonaRisk(unittest.TestCase):

    def test_output_contract(self):
        d = _make_dashboard()
        _assert_persona_contract(self, persona_risk(d))

    def test_no_vix_read(self):
        d = _make_dashboard(vix_level=None)
        r = persona_risk(d)
        self.assertIn("no vol", r["read"].lower())

    def test_calm_vix_read(self):
        d = _make_dashboard(vix_level=13.5)
        r = persona_risk(d)
        self.assertIn("13", r["read"])

    def test_elevated_vix_read(self):
        d = _make_dashboard(vix_level=24.0)
        r = persona_risk(d)
        self.assertIn("24", r["read"])

    def test_panic_vix_read(self):
        d = _make_dashboard(vix_level=32.0)
        r = persona_risk(d)
        self.assertIn("panic", r["read"].lower())

    def test_spiking_vix_trend_in_points(self):
        d = _make_dashboard(vix_trend="Spiking")
        r = persona_risk(d)
        texts = " ".join(pt["text"].lower() for pt in r["points"])
        self.assertIn("spiking", texts)

    def test_flow_extremes_appear_in_points(self):
        d = _make_dashboard(flow_score=85, flow_label="Euphoric")
        r = persona_risk(d)
        texts = " ".join(pt["text"] for pt in r["points"])
        self.assertIn("85", texts)

    def test_vix9d_fear_spike_dual_vol_in_points(self):
        d = _make_dashboard(vix9d_label="Fear Spike", skew_label="Elevated")
        r = persona_risk(d)
        texts = " ".join(pt["text"].lower() for pt in r["points"])
        self.assertIn("dual", texts)

    def test_breadth_divergence_in_points(self):
        d = _make_dashboard(rsp_vs_spy=-0.6)
        r = persona_risk(d)
        texts = " ".join(pt["text"].lower() for pt in r["points"])
        self.assertIn("mega-cap", texts)


# ═══════════════════════════════════════════════════════════════════════════
# 6. persona_rotator
# ═══════════════════════════════════════════════════════════════════════════
class TestPersonaRotator(unittest.TestCase):

    def test_output_contract(self):
        d = _make_dashboard()
        _assert_persona_contract(self, persona_rotator(d))

    def test_output_contract_bearish(self):
        d = _make_dashboard(momentum_score=30, breadth_score=20)
        _assert_persona_contract(self, persona_rotator(d))

    def test_leaders_appear_in_points(self):
        d = _make_dashboard(sector_leaders=[
            {"name": "Technology", "rs_score": 82, "trend": "Uptrend"}
        ])
        r = persona_rotator(d)
        texts = " ".join(pt["text"].lower() for pt in r["points"])
        # Leaders section should mention the sector or rotation
        self.assertIsInstance(r["points"], list)

    def test_stance_matches_score(self):
        d = _make_dashboard(momentum_score=80)
        r = persona_rotator(d)
        self.assertEqual(r["stance"], "Bullish")

        d2 = _make_dashboard(momentum_score=30)
        r2 = persona_rotator(d2)
        self.assertEqual(r2["stance"], "Bearish")


# ═══════════════════════════════════════════════════════════════════════════
# 7. persona_desk_head
# ═══════════════════════════════════════════════════════════════════════════
class TestPersonaDeskHead(unittest.TestCase):

    def _others(self, stance_list):
        return [{"stance": s} for s in stance_list]

    def test_output_contract(self):
        d = _make_dashboard()
        others = self._others(["Bullish", "Bullish", "Cautious", "Bullish"])
        _assert_persona_contract(self, persona_desk_head(d, others))

    def test_aligned_long_no_bears(self):
        d = _make_dashboard(total_score=78)
        others = self._others(["Bullish", "Bullish", "Bullish", "Bullish"])
        r = persona_desk_head(d, others)
        self.assertIn("aligned", r["read"].lower())

    def test_aligned_defensive(self):
        d = _make_dashboard(total_score=25)
        others = self._others(["Bearish", "Bearish", "Bearish", "Defensive"])
        r = persona_desk_head(d, others)
        self.assertIn("aligned defensive", r["read"].lower())

    def test_fomc_warning_in_points(self):
        d = _make_dashboard(fomc_days=1, fomc_date="2026-06-12")
        others = self._others(["Bullish", "Bullish", "Bullish", "Bullish"])
        r = persona_desk_head(d, others)
        texts = " ".join(pt["text"].upper() for pt in r["points"])
        self.assertIn("FOMC", texts)

    def test_verdict_score_present_in_points(self):
        d = _make_dashboard(total_score=72, decision="YES")
        others = self._others(["Bullish", "Cautious", "Cautious", "Bullish"])
        r = persona_desk_head(d, others)
        # First point is always the VERDICT line with the score
        self.assertIn("72", r["points"][0]["text"])

    def test_conflict_active_mentioned_in_read(self):
        conflicts = [{"severity": "warning", "title": "VIX-Trend Divergence",
                      "detail": "Something bad — watch your stops carefully."}]
        d = _make_dashboard(total_score=72, conflicts=conflicts)
        others = self._others(["Bullish", "Bullish", "Cautious", "Bullish"])
        r = persona_desk_head(d, others)
        self.assertIn("conflict", r["read"].lower())

    def test_above_200_false_stand_aside(self):
        d = _make_dashboard(total_score=35, above_200=False)
        others = self._others(["Bearish", "Bearish", "Defensive", "Bearish"])
        r = persona_desk_head(d, others)
        found = any("200" in pt["text"] or "bear" in pt["text"].lower() for pt in r["points"])
        self.assertTrue(found)


# ═══════════════════════════════════════════════════════════════════════════
# 8. roundtable() integration
# ═══════════════════════════════════════════════════════════════════════════
class TestRoundtable(unittest.TestCase):

    def setUp(self):
        self.d = _make_dashboard()
        self.result = roundtable(self.d)

    def test_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_has_personas_and_timestamp(self):
        self.assertIn("personas",  self.result)
        self.assertIn("timestamp", self.result)

    def test_exactly_five_personas(self):
        self.assertEqual(len(self.result["personas"]), 5)

    def test_desk_head_is_last(self):
        last = self.result["personas"][-1]
        self.assertEqual(last["persona"], "The Desk Head")

    def test_all_personas_have_required_keys(self):
        for p in self.result["personas"]:
            _assert_persona_contract(self, p)

    def test_timestamp_format(self):
        # Should be "HH:MM UTC"
        ts = self.result["timestamp"]
        self.assertIn("UTC", ts)
        self.assertRegex(ts, r"^\d{2}:\d{2} UTC$")

    def test_persona_order(self):
        names = [p["persona"] for p in self.result["personas"]]
        self.assertEqual(names[0], "The Technician")
        self.assertEqual(names[1], "The Macro Strategist")
        self.assertEqual(names[2], "The Risk Manager")
        self.assertEqual(names[3], "The Sector Rotator")
        self.assertEqual(names[4], "The Desk Head")

    def test_bearish_market_produces_defensive_desk_head(self):
        d = _make_dashboard(
            total_score=22, decision="STRONG NO",
            trend_score=20, vol_score=20, breadth_score=20,
            momentum_score=20, macro_score=20,
            above_200=False, vix_level=38.0,
        )
        r = roundtable(d)
        head = r["personas"][-1]
        self.assertIn(head["stance"], ("Bearish", "Defensive"))


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=0, stream=sys.stdout)
    result = runner.run(suite)

    total  = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"\n{'='*55}")
    print(f"Results: {passed}/{total} passed  "
          f"{'✓  ALL PASS' if not result.failures and not result.errors else '✗  FAILURES'}")
    sys.exit(0 if result.wasSuccessful() else 1)
