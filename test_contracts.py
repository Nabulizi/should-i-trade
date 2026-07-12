"""test_contracts.py - Runtime schema contracts for public payloads.

These tests keep the TypedDict documentation in models.py aligned with the
actual dictionaries returned by the app. They run fully offline by patching the
market-data fetch phase with deterministic fixtures.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scoring
from models import (
    DashboardResult,
    DataCoverage,
    DataQuality,
    DecisionBand,
    MarketState,
    SpyStreak,
)


def _q(price: float, change: float = 0.2) -> dict:
    return {
        "price": price,
        "prevClose": price / (1 + change / 100),
        "changePct": change,
        "source": "fixture",
    }


def _closes(n: int = 252, start: float = 100.0, step: float = 0.1) -> list[float]:
    return [round(start + i * step, 4) for i in range(n)]


def _fixture_instruments() -> dict:
    all_symbols = scoring.CORE_SYMBOLS + scoring.SECTOR_SYMBOLS + scoring.INDUSTRY_SYMBOLS
    quotes = {sym: _q(100 + i, 0.2) for i, sym in enumerate(all_symbols)}
    quotes.update({
        "SPY": _q(450, 0.4),
        "QQQ": _q(390, 0.3),
        "RSP": _q(150, 0.5),
        "^VIX": _q(17, -1.0),
        "^VIX3M": _q(19, -0.2),
        "^VIX9D": _q(16, -0.4),
        "^SKEW": _q(130, 0.0),
        "^TNX": _q(4.2, 0.0),
        "^IRX": _q(4.0, 0.0),
        "DX-Y.NYB": _q(102, -0.2),
        "HYG": _q(80, 0.1),
        "LQD": _q(110, 0.0),
        "TLT": _q(95, 0.2),
        "GLD": _q(210, -0.1),
        "IWM": _q(205, 0.6),
        "TQQQ": _q(65, 1.2),
        "SQQQ": _q(20, -1.1),
        "UVXY": _q(15, -2.0),
    })

    histories = {
        "SPY": _closes(252, 350, 0.4),
        "QQQ": _closes(252, 300, 0.3),
        "RSP": _closes(252, 120, 0.12),
        "^VIX": _closes(252, 18, -0.005),
        "^TNX": _closes(60, 4.5, -0.004),
        "DX-Y.NYB": _closes(60, 104, -0.02),
        "HYG": _closes(60, 78, 0.03),
        "LQD": _closes(60, 109, 0.01),
    }
    histories.update({sym: _closes(252, 90 + i, 0.08)
                      for i, sym in enumerate(scoring.SECTOR_SYMBOLS)})

    spy_closes = histories["SPY"]
    return {
        "all_symbols": all_symbols,
        "quotes": quotes,
        "histories": histories,
        "spy_ohlcv": {
            "closes": spy_closes,
            "highs": [c + 1 for c in spy_closes],
            "lows": [c - 1 for c in spy_closes],
            "volumes": [10_000_000 for _ in spy_closes],
        },
        "btc_q": _q(65000, 0.8),
        "btc_closes": _closes(252, 50000, 70),
        "fng_stock": {"available": False},
        "fng_crypto": {"available": False},
        "futures_tape": {"valid": False},
        "spy_last_bar_date": None,
    }


KNOWN_PILLAR_NAMES = {"trend", "breadth", "momentum", "volatility", "macro"}


def _run_with_fixtures() -> dict:
    """Run compute_dashboard() with deterministic fixture data."""
    with patch("scoring._fetch_instruments", return_value=_fixture_instruments()), \
         patch("scoring.market_state", return_value={
             "state": "open", "label": "Market Open", "color": "green",
             "et_time": "10:30 ET", "et_date": "Wed Jun 10",
         }), \
         patch("scoring.fomc_proximity", return_value={
             "days_until": 20, "date_pretty": "Jun 30",
             "label": "20d to FOMC", "color": "green",
         }), \
         patch("scoring.opex_proximity", return_value={
             "days_until": 8, "date_pretty": "Jun 19",
             "label": "OpEx in 8d", "color": "gray",
             "kind": "Monthly OpEx",
         }), \
         patch("scoring.seasonality", return_value={
             "score_adj": 0, "label": "June Neutral",
             "bias": "Neutral", "color": "yellow",
         }), \
         patch("scoring.earnings_season", return_value={
             "in_season": False, "label": "Q2 Earnings",
             "days_until": 30, "color": "gray",
         }), \
         patch("scoring.econ_proximity", return_value=[
             {"type": "CPI", "name": "CPI", "days_until": 5},
             {"type": "PPI", "name": "PPI", "days_until": 6},
         ]):
        return scoring.compute_dashboard()


class TestDashboardContracts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.payload = _run_with_fixtures()

    def test_keys_match_dashboard_result_typeddict(self):
        """Every returned key is modelled; every required key is present."""
        modeled_keys = set(DashboardResult.__required_keys__) | set(DashboardResult.__optional_keys__)
        self.assertFalse(set(self.payload) - modeled_keys,
                         "Payload has undocumented keys")
        self.assertFalse(set(DashboardResult.__required_keys__) - set(self.payload),
                         "Payload is missing required keys")

    def test_total_score_is_bounded_int(self):
        score = self.payload["total_score"]
        self.assertIsInstance(score, int)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_decision_is_known_value(self):
        known = {b["decision"] for b in scoring.DECISION_BANDS}
        self.assertIn(self.payload["decision"], known)

    def test_decision_color_is_string(self):
        self.assertIsInstance(self.payload["decision_color"], str)
        self.assertTrue(self.payload["decision_color"])

    def test_timestamp_is_non_empty_string(self):
        ts = self.payload["timestamp"]
        self.assertIsInstance(ts, str)
        self.assertTrue(ts, "timestamp must not be empty")

    def test_vol_target_is_none_or_well_formed(self):
        self.assertIn("vol_target", self.payload)
        vt = self.payload["vol_target"]
        if vt is not None:
            self.assertIsInstance(vt["exposure_pct"], float)
            self.assertIsInstance(vt["realized_vol_pct"], float)
            self.assertGreaterEqual(vt["exposure_pct"], 0.0)
            self.assertLessEqual(vt["exposure_pct"], 100.0)
            # Rounded to 2 decimals; near-zero-vol fixtures may round to 0.0.
            self.assertGreaterEqual(vt["realized_vol_pct"], 0.0)
            # P1-008: annualized units exposed alongside the legacy daily field
            self.assertIn("realized_annual_vol_pct", vt)
            self.assertIn("target_annual_vol_pct", vt)
            self.assertIn("window_days", vt)
            self.assertAlmostEqual(vt["target_annual_vol_pct"], 7.8, places=1)

    def test_positions_are_condition_bands_not_exposure_directives(self):
        """P1-010 (D-001): the band 'position' labels describe conditions —
        the only exposure percentage on the dashboard is the vol budget."""
        for band in scoring.DECISION_BANDS:
            self.assertNotIn("EXPOSURE", band["position"])
            self.assertIn("CONDITIONS", band["position"])
        self.assertIn(self.payload["position_size"],
                      {b["position"] for b in scoring.DECISION_BANDS})

    def test_vol_target_annualization_consistency(self):
        """exposure must equal clamp(target/realized) in annual units too —
        the annualization changes labels, not the number (P1-008)."""
        vt = self.payload["vol_target"]
        if vt is None or vt["realized_annual_vol_pct"] <= 0:
            self.skipTest("no vol_target in fixture payload")
        expected = min(100.0, 100.0 * vt["target_annual_vol_pct"] / vt["realized_annual_vol_pct"])
        self.assertAlmostEqual(vt["exposure_pct"], expected, delta=1.5)  # rounding of components

    def test_pillars_contain_all_five(self):
        self.assertEqual(set(self.payload["pillars"].keys()), KNOWN_PILLAR_NAMES)

    def test_each_pillar_has_required_fields(self):
        for name, pillar in self.payload["pillars"].items():
            with self.subTest(pillar=name):
                self.assertIn("score", pillar, f"{name}: missing 'score'")
                self.assertIn("weight", pillar, f"{name}: missing 'weight'")
                self.assertIn("reasons", pillar, f"{name}: missing 'reasons'")
                self.assertIn("details", pillar, f"{name}: missing 'details'")
                self.assertIsInstance(pillar["score"], int, f"{name}: score not int")
                self.assertIsInstance(pillar["reasons"], list, f"{name}: reasons not list")
                self.assertIsInstance(pillar["details"], dict, f"{name}: details not dict")
                self.assertIsInstance(pillar["weight"], int, f"{name}: weight not int")
                self.assertGreaterEqual(pillar["score"], 0)
                self.assertLessEqual(pillar["score"], 100)

    def test_pillar_weights_sum_to_100(self):
        total = sum(p["weight"] for p in self.payload["pillars"].values())
        self.assertEqual(total, 100, f"Pillar weights sum to {total}, expected 100")

    def test_decision_bands_structure(self):
        bands = self.payload["decision_bands"]
        self.assertIsInstance(bands, list)
        self.assertTrue(bands, "decision_bands must not be empty")
        self.assertEqual([b["min"] for b in bands],
                         sorted((b["min"] for b in bands), reverse=True))
        self.assertEqual(bands[-1]["min"], 0)
        required = set(DecisionBand.__required_keys__)
        for band in bands:
            with self.subTest(band=band):
                self.assertFalse(required - set(band))
                self.assertGreaterEqual(band["min"], 0)
                self.assertLessEqual(band["min"], 100)

    def test_ticker_is_list(self):
        self.assertIsInstance(self.payload["ticker"], list)

    def test_conflicts_is_list(self):
        self.assertIsInstance(self.payload["conflicts"], list)

    def test_data_sources_is_dict(self):
        self.assertIsInstance(self.payload["data_sources"], dict)

    def test_data_sources_split_quote_and_history(self):
        """P0-022: quote and history provenance are labeled separately, and a
        live level is never blanket-labeled with the official history
        publisher (the old payload hardcoded vix='CBOE', tnx='US Treasury')."""
        ds = self.payload["data_sources"]
        for key in ("vix", "tnx", "spy", "btc"):
            with self.subTest(source=key):
                self.assertIsInstance(ds[key], dict)
                self.assertIn("quote", ds[key])
                self.assertIn("history", ds[key])
        # Fixture quotes come from the generic fetcher — the quote label must
        # not claim the official publishers.
        self.assertNotIn(ds["vix"]["quote"], ("CBOE",))
        self.assertNotIn(ds["tnx"]["quote"], ("US Treasury",))

    def test_market_state_shape(self):
        required = set(MarketState.__required_keys__)
        self.assertFalse(required - set(self.payload["market_state"]))
        self.assertIn(self.payload["market_state"]["state"],
                      {"open", "closed", "premarket", "afterhours", "weekend"})
        self.assertTrue(self.payload["market_state"]["et_time"])

    def test_data_coverage_shape(self):
        coverage = self.payload["data_coverage"]
        self.assertFalse(set(DataCoverage.__required_keys__) - set(coverage))
        self.assertIsInstance(coverage["requested"], int)
        self.assertIsInstance(coverage["fetched"], int)
        self.assertIsInstance(coverage["failed"], list)
        self.assertGreaterEqual(coverage["requested"], coverage["fetched"])

    def test_data_quality_shape(self):
        quality = self.payload["data_quality"]
        self.assertFalse(set(DataQuality.__required_keys__) - set(quality))
        self.assertIsInstance(quality["valid"], bool)
        self.assertGreaterEqual(quality["coverage_pct"], 0)
        self.assertLessEqual(quality["coverage_pct"], 100)
        self.assertIsInstance(quality["critical_missing"], list)
        self.assertIsInstance(quality["critical_history_missing"], list)
        self.assertIsInstance(quality["message"], str)
        self.assertTrue(quality["message"])

    def test_spy_streak_shape(self):
        streak = self.payload["spy_streak"]
        self.assertFalse(set(SpyStreak.__required_keys__) - set(streak))
        self.assertIn(streak["direction"], {"up", "down", "flat"})
        self.assertIsInstance(streak["days"], int)

    def test_raw_score_leq_total_score_or_safety_applied(self):
        """raw_total_score >= total_score (safety cap can only reduce)."""
        self.assertGreaterEqual(self.payload["raw_total_score"], self.payload["total_score"])

    def test_hysteresis_fields_present_and_consistent(self):
        """P1-030: payload reports the natural band and whether stickiness
        was applied (fixture run passes no prev_decision -> natural)."""
        self.assertIn(self.payload["natural_decision"],
                      {b["decision"] for b in scoring.DECISION_BANDS} | {"DATA UNAVAILABLE"})
        self.assertFalse(self.payload["hysteresis_applied"])

    def test_model_version_present(self):
        """P1-028 / D-006: numerical changes are versioned in the payload."""
        self.assertEqual(self.payload["model_version"], scoring.MODEL_VERSION)
        self.assertRegex(scoring.MODEL_VERSION, r"^v\d+\.\d+$")

    def test_as_of_distinguishes_calc_and_observation_time(self):
        """P1-003/P1-005: computation time vs market-data time are separate."""
        as_of = self.payload["as_of"]
        for key in ("calculated_at", "market_data_as_of", "history_last_bar", "session"):
            self.assertIn(key, as_of)
        from datetime import datetime
        datetime.fromisoformat(as_of["calculated_at"])   # raises if malformed
        self.assertIn(as_of["session"],
                      {"open", "closed", "premarket", "afterhours", "weekend"})

    def test_reliability_shape_and_level(self):
        rel = self.payload["reliability"]
        self.assertIn(rel["level"], {"high", "medium", "low", "none"})
        self.assertIsInstance(rel["coverage_pct"], float)
        self.assertIsInstance(rel["critical_ok"], bool)
        self.assertIsInstance(rel["boundary_distance"], int)
        self.assertIsInstance(rel["pillar_spread"], int)


class TestBandHysteresis(unittest.TestCase):
    """P1-030: sticky band labels near boundaries; safety paths bypass."""

    def test_boundary_wiggle_does_not_churn(self):
        # 54 -> 55 -> 54 with prev DE-RISK stays DE-RISK throughout
        (dec, _, _), applied = scoring.decision_with_hysteresis(55, "DE-RISK")
        self.assertEqual(dec, "DE-RISK")
        self.assertTrue(applied)
        (dec, _, _), applied = scoring.decision_with_hysteresis(54, "SELECTIVE")
        self.assertEqual(dec, "SELECTIVE")
        self.assertTrue(applied)

    def test_clearing_the_boundary_flips(self):
        (dec, _, _), applied = scoring.decision_with_hysteresis(58, "DE-RISK")
        self.assertEqual(dec, "SELECTIVE")
        self.assertFalse(applied)
        (dec, _, _), applied = scoring.decision_with_hysteresis(52, "SELECTIVE")
        self.assertEqual(dec, "DE-RISK")
        self.assertFalse(applied)

    def test_multi_band_jump_is_never_held(self):
        (dec, _, _), applied = scoring.decision_with_hysteresis(80, "DE-RISK")
        self.assertEqual(dec, "CONSTRUCTIVE")
        self.assertFalse(applied)

    def test_no_prev_or_unknown_prev_returns_natural(self):
        (dec, _, _), applied = scoring.decision_with_hysteresis(55, None)
        self.assertEqual((dec, applied), ("SELECTIVE", False))
        (dec, _, _), applied = scoring.decision_with_hysteresis(55, "NO SUCH BAND")
        self.assertEqual((dec, applied), ("SELECTIVE", False))

    def test_same_band_is_a_no_op(self):
        (dec, _, _), applied = scoring.decision_with_hysteresis(60, "SELECTIVE")
        self.assertEqual((dec, applied), ("SELECTIVE", False))

    def test_position_matches_held_band(self):
        (dec, color, pos), _ = scoring.decision_with_hysteresis(55, "DE-RISK")
        band = next(b for b in scoring.DECISION_BANDS if b["decision"] == dec)
        self.assertEqual((color, pos), (band["color"], band["position"]))


class TestReliabilityIndependence(unittest.TestCase):
    """D-004: reliability must reflect input trust, never score direction."""

    _GOOD_DQ = {"valid": True, "coverage_pct": 100.0,
                "critical_missing": [], "critical_history_missing": []}
    _PILLARS = {k: {"score": 50} for k in ("volatility", "trend", "breadth",
                                           "momentum", "macro")}

    def test_low_score_with_clean_data_is_high_reliability(self):
        rel = scoring.build_reliability(self._GOOD_DQ, self._PILLARS, 20)
        self.assertEqual(rel["level"], "high")

    def test_high_score_with_clean_data_is_high_reliability(self):
        rel = scoring.build_reliability(self._GOOD_DQ, self._PILLARS, 95)
        self.assertEqual(rel["level"], "high")

    def test_high_score_with_poor_coverage_is_low(self):
        dq = {**self._GOOD_DQ, "coverage_pct": 82.0}
        rel = scoring.build_reliability(dq, self._PILLARS, 95)
        self.assertEqual(rel["level"], "low")

    def test_score_on_a_band_edge_is_not_high(self):
        rel = scoring.build_reliability(self._GOOD_DQ, self._PILLARS, 55)
        self.assertNotEqual(rel["level"], "high")

    def test_invalid_data_is_none(self):
        dq = {**self._GOOD_DQ, "valid": False}
        rel = scoring.build_reliability(dq, self._PILLARS, 50)
        self.assertEqual(rel["level"], "none")


class TestLabelContracts(unittest.TestCase):
    """P0-002/P0-003/P0-004: producer-consumer label contracts.

    analysis.py and scoring.detect_conflicts() branch on string labels emitted
    by score_volatility(). These tests fail when a compared label can no longer
    be produced (the dead-SKEW-branch bug class) or a declared label becomes
    unreachable.
    """

    @staticmethod
    def _vol_details(vix: float, skew: float | None = None,
                     vix9d: float | None = None) -> dict:
        quotes = {"^VIX": _q(vix, 0.0)}
        if skew is not None:
            quotes["^SKEW"] = _q(skew, 0.0)
        if vix9d is not None:
            quotes["^VIX9D"] = _q(vix9d, 0.0)
        return scoring.score_volatility(quotes, _closes(60, 15, 0.01))["details"]

    def test_every_declared_skew_label_is_reachable(self):
        emitted = {
            self._vol_details(vix, skew=skew)["skew_label"]
            for vix, skew in [
                (15, 155),   # calm VIX + extreme SKEW  -> Cautious Optimism
                (25, 155),   # high VIX + extreme SKEW  -> Compound Fear
                (15, 145),   # calm VIX + elevated SKEW -> Cautious Bulls
                (25, 145),   # high VIX + elevated SKEW -> Elevated Hedging
                (15, 130),   # normal SKEW              -> Normal
                (15, 115),   # low SKEW                 -> Complacent
            ]
        }
        emitted.add(self._vol_details(15)["skew_label"])  # no SKEW quote -> N/A
        self.assertEqual(emitted, set(scoring.SKEW_LABELS))

    def test_every_declared_vix9d_label_is_reachable(self):
        emitted = {
            self._vol_details(20, vix9d=v9)["vix9d_label"]
            for v9 in (23, 17, 19)   # ratio 1.15 / 0.85 / 0.95
        }
        emitted.add(self._vol_details(20)["vix9d_label"])  # no VIX9D quote -> N/A
        self.assertEqual(emitted, set(scoring.VIX9D_LABELS))

    def test_hedging_labels_are_a_subset_of_skew_labels(self):
        self.assertTrue(set(scoring.SKEW_HEDGING_LABELS) <= set(scoring.SKEW_LABELS))

    def test_compared_label_literals_are_producible(self):
        """AST audit: any string literal compared against a skew/vix9d label
        variable in analysis.py or scoring.py must be an emittable label."""
        import ast

        label_sets = {
            "skew_label": set(scoring.SKEW_LABELS),
            "skew_l": set(scoring.SKEW_LABELS),
            "vix9d_label": set(scoring.VIX9D_LABELS),
            "vix9d_l": set(scoring.VIX9D_LABELS),
        }
        here = os.path.dirname(os.path.abspath(__file__))
        offenders = []
        for fname in ("analysis.py", "scoring.py"):
            with open(os.path.join(here, fname)) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                names = {n.id for n in ast.walk(node.left) if isinstance(n, ast.Name)}
                watched = names & set(label_sets)
                if not watched:
                    continue
                literals = {
                    c.value for comp in node.comparators for c in ast.walk(comp)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)
                }
                for var in watched:
                    for lit in literals - label_sets[var]:
                        offenders.append(f"{fname}:{node.lineno} compares {var} to {lit!r}")
        self.assertEqual(offenders, [],
                         "Labels compared but never emitted by scoring.py:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
