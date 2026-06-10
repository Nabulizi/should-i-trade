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
from models import DashboardResult


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


class TestDashboardContracts(unittest.TestCase):

    def test_compute_dashboard_keys_match_dashboard_result_typeddict(self):
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
            payload = scoring.compute_dashboard()

        modeled_keys = set(DashboardResult.__required_keys__) | set(DashboardResult.__optional_keys__)
        self.assertFalse(set(payload) - modeled_keys)
        self.assertFalse(set(DashboardResult.__required_keys__) - set(payload))


if __name__ == "__main__":
    unittest.main()
