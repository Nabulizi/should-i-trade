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


if __name__ == "__main__":
    unittest.main()
