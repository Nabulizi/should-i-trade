"""test_backtest_stats.py - Contracts for pure backtest analytics."""

from __future__ import annotations

import math
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_stats


def make_rows(n, *, total=60.0, decision="SELECTIVE", fwd1=0.1, fwd5=0.5,
              fwd20=1.0, start="2020-01-01"):
    """Build n synthetic BacktestRows. Scalar args broadcast; list args map per-row."""
    start_date = date.fromisoformat(start)

    def at(value, i):
        return value[i] if isinstance(value, list) else value

    rows = []
    for i in range(n):
        rows.append({
            "date": (start_date + timedelta(days=i)).isoformat(),
            "total": float(at(total, i)),
            "raw_total": float(at(total, i)),
            "decision": at(decision, i),
            "above_200": True,
            "v": 50.0, "tr": 50.0, "br": 50.0, "mo": 50.0, "ma": 50.0,
            "rsi2": None, "dist20": None,
            "fwd1": float(at(fwd1, i)),
            "fwd5": float(at(fwd5, i)),
            "fwd20": float(at(fwd20, i)),
        })
    return rows


class TestSimulateWithExposures(unittest.TestCase):

    def test_full_exposure_compounds_fwd5_blocks(self):
        # 10 rows = 2 blocks; block starts at rows 0 and 5. fwd5 = +1% and +2%.
        rows = make_rows(10, fwd5=[1.0] * 5 + [2.0] * 5)
        result = backtest_stats.simulate_with_exposures(rows, [1.0] * 10, "bh")
        self.assertAlmostEqual(result["total_return_pct"], (1.01 * 1.02 - 1) * 100, places=9)
        self.assertEqual(result["total_blocks"], 2)
        self.assertEqual(result["invested_blocks"], 2)
        self.assertAlmostEqual(result["exposure_pct"], 100.0, places=9)

    def test_binary_exposures_skip_uninvested_blocks(self):
        rows = make_rows(10, fwd5=[1.0] * 5 + [2.0] * 5)
        exposures = [1.0] * 5 + [0.0] * 5
        result = backtest_stats.simulate_with_exposures(rows, exposures, "timing")
        self.assertAlmostEqual(result["total_return_pct"], 1.0, places=9)
        self.assertEqual(result["invested_blocks"], 1)
        self.assertAlmostEqual(result["exposure_pct"], 50.0, places=9)

    def test_costs_charged_on_exposure_changes_including_entry(self):
        # Exposure path by block: 1.0 then 0.0 -> two changes (entry 0->1, exit 1->0).
        rows = make_rows(10, fwd5=[1.0] * 5 + [2.0] * 5)
        exposures = [1.0] * 5 + [0.0] * 5
        clean = backtest_stats.simulate_with_exposures(rows, exposures, "t", cost_bps=0.0)
        costed = backtest_stats.simulate_with_exposures(rows, exposures, "t", cost_bps=10.0)
        # Block 1: (0.01 - 0.001), Block 2: (0.0 - 0.001)
        expected = ((1 + 0.01 - 0.001) * (1 - 0.001) - 1) * 100
        self.assertAlmostEqual(costed["total_return_pct"], expected, places=9)
        self.assertLess(costed["total_return_pct"], clean["total_return_pct"])

    def test_higher_costs_never_increase_return(self):
        rows = make_rows(40, fwd5=[0.5, -0.3, 1.2, -0.8] * 10)
        exposures = ([1.0] * 5 + [0.0] * 5) * 4
        returns = [
            backtest_stats.simulate_with_exposures(rows, exposures, "t", cost_bps=bps)["total_return_pct"]
            for bps in (0.0, 5.0, 10.0, 20.0)
        ]
        self.assertEqual(returns, sorted(returns, reverse=True))

    def test_misaligned_exposures_raise(self):
        rows = make_rows(10)
        with self.assertRaises(ValueError):
            backtest_stats.simulate_with_exposures(rows, [1.0] * 9, "bad")


class TestCountFlips(unittest.TestCase):

    def test_flip_count_on_block_boundaries(self):
        # Block exposures: 1, 0, 1 -> 3 changes (entry, exit, re-entry).
        exposures = [1.0] * 5 + [0.0] * 5 + [1.0] * 5
        self.assertEqual(backtest_stats.count_flips(exposures), 3)

    def test_constant_exposure_flips_once_at_entry(self):
        self.assertEqual(backtest_stats.count_flips([0.6] * 20), 1)

    def test_never_invested_never_flips(self):
        self.assertEqual(backtest_stats.count_flips([0.0] * 20), 0)


if __name__ == "__main__":
    unittest.main()
