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


class TestVolTarget(unittest.TestCase):

    def test_realized_vol_warmup_is_none_then_trailing_std(self):
        rows = make_rows(30, fwd1=[1.0, -1.0] * 15)
        vols = backtest_stats.realized_vol_series(rows)
        self.assertTrue(all(v is None for v in vols[:backtest_stats.VOL_WINDOW]))
        # Trailing 20 of alternating +1/-1 has a known sample std.
        import statistics
        expected = statistics.stdev([1.0, -1.0] * 10)
        self.assertAlmostEqual(vols[backtest_stats.VOL_WINDOW], expected, places=9)

    def test_realized_vol_has_no_lookahead(self):
        base = make_rows(60, fwd1=[0.5, -0.4, 0.9, -0.2] * 15)
        vols_before = backtest_stats.realized_vol_series(base)
        mutated = [dict(r) for r in base]
        mutated[45]["fwd1"] = 99.0  # shock a future return
        vols_after = backtest_stats.realized_vol_series(mutated)
        # vols at index i use fwd1[i-20:i]; indices <= 45 must be unaffected.
        for i in range(46):
            self.assertEqual(vols_before[i], vols_after[i])

    def test_constant_vol_yields_constant_exposure(self):
        rows = make_rows(100, fwd1=[1.0, -1.0] * 50)
        exposures = backtest_stats.calibrate_vol_exposures(rows, 60.0)
        post_warmup = exposures[backtest_stats.VOL_WINDOW:]
        self.assertTrue(all(abs(e - post_warmup[0]) < 1e-9 for e in post_warmup))

    def test_calibration_hits_target_exposure(self):
        # Two vol regimes: calm first half, stormy second half.
        fwd1 = [0.2, -0.2] * 25 + [2.0, -2.0] * 25
        rows = make_rows(100, fwd1=fwd1)
        exposures = backtest_stats.calibrate_vol_exposures(rows, 60.0)
        block_exposures = [exposures[i] for i in range(0, 100, backtest_stats.BLOCK_DAYS)]
        avg = sum(block_exposures) / len(block_exposures)
        self.assertAlmostEqual(avg, 0.60, delta=0.005)
        self.assertTrue(all(0.0 <= e <= 1.0 for e in exposures))

    def test_vol_target_strategy_returns_labeled_result(self):
        rows = make_rows(100, fwd1=[0.3, -0.2] * 50, fwd5=[0.5, -0.1] * 50)
        result = backtest_stats.vol_target_strategy(rows, 60.0)
        self.assertIn("Vol-target 60%", result["label"])
        self.assertAlmostEqual(result["exposure_pct"], 60.0, delta=0.5)


class TestYearlyTable(unittest.TestCase):

    def _two_year_rows(self):
        # 2020: scores below 55 (timing flat). 2021: scores above 55 (timing long).
        rows_2020 = make_rows(40, total=40.0, fwd5=1.0, start="2020-01-01")
        rows_2021 = make_rows(40, total=80.0, fwd5=2.0, start="2021-01-01")
        return rows_2020 + rows_2021

    def test_years_days_and_returns(self):
        rows = self._two_year_rows()
        vol_exposures = [0.6] * len(rows)
        table = backtest_stats.yearly_table(rows, 55.0, 0.6, vol_exposures)
        self.assertEqual([y["year"] for y in table], ["2020", "2021"])
        self.assertEqual([y["days"] for y in table], [40, 40])
        # 2020: timing never invested -> 0% return; B&H compounds 8 blocks of +1%.
        self.assertAlmostEqual(table[0]["timing_return_pct"], 0.0, places=9)
        self.assertAlmostEqual(table[0]["buy_hold_return_pct"], (1.01 ** 8 - 1) * 100, places=9)
        # 2021: timing fully invested -> equals B&H for the year.
        self.assertAlmostEqual(
            table[1]["timing_return_pct"], table[1]["buy_hold_return_pct"], places=9)

    def test_beat_benchmark_flag(self):
        rows = self._two_year_rows()
        vol_exposures = [0.6] * len(rows)
        table = backtest_stats.yearly_table(rows, 55.0, 0.6, vol_exposures)
        # 2020: timing 0% vs matched 0.6*1% per block -> did not beat.
        self.assertFalse(table[0]["beat_benchmark"])
        # 2021: timing 2% vs matched 1.2% per block -> beat.
        self.assertTrue(table[1]["beat_benchmark"])

    def test_mean_score_per_year(self):
        rows = self._two_year_rows()
        table = backtest_stats.yearly_table(rows, 55.0, 0.6, [0.6] * len(rows))
        self.assertAlmostEqual(table[0]["mean_score"], 40.0, places=9)
        self.assertAlmostEqual(table[1]["mean_score"], 80.0, places=9)


class TestBootstrap(unittest.TestCase):

    def test_deterministic_across_runs(self):
        rows = make_rows(100, total=list(range(100)), fwd5=[0.4, -0.3] * 50)
        stat = backtest_stats.ic_statistic(5)
        a = backtest_stats.block_bootstrap_ci(rows, stat, n_resamples=200)
        b = backtest_stats.block_bootstrap_ci(rows, stat, n_resamples=200)
        self.assertEqual(a, b)

    def test_constant_series_zero_width_ci(self):
        rows = make_rows(100, fwd5=0.7)
        stat = lambda rs: sum(r["fwd5"] for r in rs) / len(rs)
        point, lo, hi = backtest_stats.block_bootstrap_ci(rows, stat, n_resamples=200)
        self.assertAlmostEqual(point, 0.7, places=9)
        self.assertAlmostEqual(lo, 0.7, places=9)
        self.assertAlmostEqual(hi, 0.7, places=9)

    def test_strong_signal_excludes_zero(self):
        rows = make_rows(100, fwd5=[0.8, 1.2] * 50)
        stat = lambda rs: sum(r["fwd5"] for r in rs) / len(rs)
        point, lo, hi = backtest_stats.block_bootstrap_ci(rows, stat, n_resamples=200)
        self.assertGreater(lo, 0.0)
        self.assertLessEqual(lo, point)
        self.assertGreaterEqual(hi, point)

    def test_too_few_rows_raise(self):
        rows = make_rows(10)
        with self.assertRaises(ValueError):
            backtest_stats.block_bootstrap_ci(rows, lambda rs: 0.0)


class TestStatistics(unittest.TestCase):

    def test_ic_statistic_perfect_monotone_signal(self):
        # Score 0..99 and fwd5 0..99 -> Spearman IC exactly +1.
        rows = make_rows(100, total=list(range(100)),
                         fwd5=[float(x) for x in range(100)])
        self.assertAlmostEqual(backtest_stats.ic_statistic(5)(rows), 1.0, places=9)

    def test_band_mean_statistic_filters_band(self):
        rows = (make_rows(30, decision="RISK-ON", fwd5=1.0)
                + make_rows(30, decision="RISK-OFF", fwd5=-2.0, start="2020-03-01"))
        self.assertAlmostEqual(
            backtest_stats.band_mean_statistic("RISK-ON")(rows), 1.0, places=9)
        self.assertAlmostEqual(
            backtest_stats.band_mean_statistic("RISK-OFF")(rows), -2.0, places=9)
        self.assertTrue(math.isnan(backtest_stats.band_mean_statistic("SELECTIVE")(rows)))

    def test_decile_spread_bottom_minus_top(self):
        # Bottom-decile scores carry fwd5=+2, top-decile scores carry fwd5=-1.
        fwd5 = [2.0] * 10 + [0.0] * 80 + [-1.0] * 10
        rows = make_rows(100, total=list(range(100)), fwd5=fwd5)
        self.assertAlmostEqual(backtest_stats.decile_spread_statistic(rows), 3.0, places=9)

    def test_ic_statistic_rejects_unsupported_horizon(self):
        rows = make_rows(50)
        with self.assertRaises(ValueError):
            backtest_stats.ic_statistic(10)(rows)


if __name__ == "__main__":
    unittest.main()
