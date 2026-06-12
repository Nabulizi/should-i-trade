# Backtest Robustness Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four robustness analytics to the backtest report — an exposure-matched vol-targeting baseline, a year-by-year table, block-bootstrap confidence intervals, and transaction-cost sensitivity — so product claims can be judged against trivial baselines, crisis concentration, noise, and costs.

**Architecture:** New pure module `backtest_stats.py` (stdlib-only, deterministic, no I/O) holds shared types, stat helpers, a generic exposure-block simulator, and the four analytics. `backtest_report.py` imports from it and renders one new strategy-table row plus three new markdown sections. No changes to `backtest.py` or the CSV schema.

**Tech Stack:** Python 3.10+ stdlib only (`math`, `random`, `typing`, `csv`). Tests: `unittest`, runnable as `python3 test_backtest_stats.py`.

**Spec:** `docs/superpowers/specs/2026-06-11-backtest-robustness-analytics-design.md`

**Branch:** `feat/backtest-robustness-analytics` (already created; spec committed).

**Conventions to follow:**
- Tests are plain `unittest.TestCase` classes with a `if __name__ == "__main__": unittest.main()` footer, like `test_backtest_report.py`.
- All report math is pure: no network, no file reads inside analytics functions, no clock reads.
- Index contract for `strategy_rows()` changes in Task 6 from 5 rows to 6 — every consumer is updated in that same task.

---

### Task 1: Create `backtest_stats.py` and move shared types/helpers

`backtest_report.py` currently owns `BacktestRow`, `StrategyResult`, and the stat helpers (`_mean`, `_median`, `_std`, `_rank`, `pearson`, `spearman`, `max_drawdown`). Move them to the new module so `backtest_stats` never imports `backtest_report` (import direction: report → stats). This is a pure refactor guarded by the existing test suite.

**Files:**
- Create: `backtest_stats.py`
- Modify: `backtest_report.py` (delete moved code, import instead)
- Test: existing `test_backtest_report.py` (must stay green, no edits)

- [ ] **Step 1: Run the existing suite to capture the green baseline**

Run: `python3 test_backtest_report.py`
Expected: `OK` (8 tests pass)

- [ ] **Step 2: Create `backtest_stats.py` with types, constants, and moved helpers**

The function bodies of `_mean`, `_median`, `_std`, `_rank`, `pearson`, `spearman`, `max_drawdown` are moved **verbatim** from `backtest_report.py:153-218` — do not rewrite them.

```python
"""
backtest_stats.py - Pure statistical analytics for the backtest report.

Offline, deterministic, stdlib-only. backtest_report.py imports from this
module; nothing here reads files, the network, or the clock. backtest_stats
must never import backtest_report.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Iterable, TypedDict


BLOCK_DAYS = 5
VOL_WINDOW = 20
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_BLOCK = 21
BOOTSTRAP_SEED = 20260611


class BacktestRow(TypedDict):
    date: str
    total: float
    raw_total: float
    decision: str
    above_200: bool
    v: float
    tr: float
    br: float
    mo: float
    ma: float
    rsi2: float | None
    dist20: float | None
    fwd1: float
    fwd5: float
    fwd20: float


class StrategyResult(TypedDict):
    label: str
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    exposure_pct: float
    invested_blocks: int
    total_blocks: int


# --- stat helpers moved verbatim from backtest_report.py ---
# _mean, _median, _std, _rank, pearson, spearman, max_drawdown
# (copy the exact bodies from backtest_report.py lines 153-218)
```

- [ ] **Step 3: Update `backtest_report.py` to import the moved code**

Delete the `BacktestRow` and `StrategyResult` class definitions and the seven helper functions from `backtest_report.py`, and delete the now-unused `math` usages check (keep `import math` — `_fmt_pct`/`_fmt_num`/`strategy` still use `math.isnan`/`math.sqrt`). Add below the existing imports:

```python
from backtest_stats import (
    BacktestRow,
    StrategyResult,
    _mean,
    _median,
    _std,
    max_drawdown,
    pearson,
    spearman,
)
```

(`_rank` is only used by `spearman`, which now lives in `backtest_stats`; do not re-import it.)

- [ ] **Step 4: Verify the refactor is behavior-neutral**

Run: `python3 test_backtest_report.py && python -m py_compile backtest_stats.py backtest_report.py`
Expected: `OK` (same 8 tests), no compile errors

- [ ] **Step 5: Commit**

```bash
git add backtest_stats.py backtest_report.py
git commit -m "refactor: move backtest types and stat helpers to backtest_stats module"
```

---

### Task 2: Generic exposure-block simulator with cost support

One simulator covers every strategy in the report: binary timing rules (exposures 0/1), constant-fraction benchmarks, and the vol-target baseline (continuous exposures). `cost_bps` is charged on each change in exposure, including the initial entry from cash, so all strategies are charged fairly.

**Files:**
- Create: `test_backtest_stats.py`
- Modify: `backtest_stats.py`

- [ ] **Step 1: Write the failing tests**

Create `test_backtest_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 test_backtest_stats.py`
Expected: FAIL/ERROR with `AttributeError: module 'backtest_stats' has no attribute 'simulate_with_exposures'`

- [ ] **Step 3: Implement `simulate_with_exposures` and `count_flips` in `backtest_stats.py`**

```python
def simulate_with_exposures(rows: list[BacktestRow], exposures: list[float],
                            label: str, cost_bps: float = 0.0) -> StrategyResult:
    """Non-overlapping 5-day block simulation with a per-row exposure series.

    The exposure used for each block is the value at the block's first row.
    cost_bps is charged on every change in block exposure, including the
    initial entry from cash: cost = |new - old| * cost_bps / 10_000.
    """
    if len(exposures) != len(rows):
        raise ValueError("exposures must have one entry per row")
    equity = 1.0
    curve = [equity]
    blocks: list[float] = []
    block_exposures: list[float] = []
    invested_blocks = 0
    prev_exposure = 0.0
    for i in range(0, len(rows), BLOCK_DAYS):
        exposure = exposures[i]
        block_return = exposure * rows[i]["fwd5"] / 100
        block_return -= abs(exposure - prev_exposure) * cost_bps / 10_000
        if exposure > 0:
            invested_blocks += 1
        equity *= 1 + block_return
        blocks.append(block_return)
        block_exposures.append(exposure)
        curve.append(equity)
        prev_exposure = exposure
    years = len(rows) / 252.0
    cagr = (equity ** (1 / years) - 1) if years > 0 and equity > 0 else float("nan")
    sd = _std(blocks)
    sharpe = (_mean(blocks) / sd * math.sqrt(252 / BLOCK_DAYS)) if sd and sd > 0 else float("nan")
    return {
        "label": label,
        "total_return_pct": (equity - 1) * 100,
        "cagr_pct": cagr * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown(curve) * 100,
        "exposure_pct": 100 * _mean(block_exposures),
        "invested_blocks": invested_blocks,
        "total_blocks": len(blocks),
    }


def count_flips(exposures: list[float], block_days: int = BLOCK_DAYS) -> int:
    """Number of block-boundary exposure changes, counting the initial entry."""
    prev = 0.0
    flips = 0
    for i in range(0, len(exposures), block_days):
        if exposures[i] != prev:
            flips += 1
        prev = exposures[i]
    return flips
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_stats.py && python3 test_backtest_report.py`
Expected: both `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_stats.py test_backtest_stats.py
git commit -m "feat: add generic exposure-block simulator with transaction costs"
```

---

### Task 3: Vol-targeting baseline (realized vol, calibration, strategy)

**Files:**
- Modify: `backtest_stats.py`
- Modify: `test_backtest_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_backtest_stats.py` (above the `__main__` footer):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 test_backtest_stats.py`
Expected: FAIL with `AttributeError: ... no attribute 'realized_vol_series'`

- [ ] **Step 3: Implement in `backtest_stats.py`**

```python
def realized_vol_series(rows: list[BacktestRow],
                        window: int = VOL_WINDOW) -> list[float | None]:
    """Trailing realized vol of daily returns, None during warmup.

    fwd1[j] is the day-j-close to day-j+1-close return, so the window for
    row i is fwd1[i-window:i] - fully known by day i's close (no lookahead).
    """
    daily = [r["fwd1"] for r in rows]
    out: list[float | None] = [None] * len(rows)
    for i in range(window, len(rows)):
        out[i] = _std(daily[i - window:i])
    return out


def calibrate_vol_exposures(rows: list[BacktestRow], target_exposure_pct: float,
                            window: int = VOL_WINDOW,
                            tolerance_pp: float = 0.5) -> list[float]:
    """Per-row exposures clamp(k / vol, 0, 1), k bisected so the average
    block exposure matches target_exposure_pct. Warmup rows (and zero-vol
    rows) hold the target exposure so all strategies cover the same dates.
    """
    vols = realized_vol_series(rows, window)
    target = target_exposure_pct / 100.0

    def exposures_for(k: float) -> list[float]:
        return [
            target if v is None or v <= 0 else min(1.0, k / v)
            for v in vols
        ]

    def avg_block_exposure(k: float) -> float:
        exps = exposures_for(k)
        return _mean([exps[i] for i in range(0, len(rows), BLOCK_DAYS)])

    lo, hi = 0.0, 1000.0
    if avg_block_exposure(hi) < target - tolerance_pp / 100:
        raise ValueError("target exposure unreachable for this vol series")
    for _ in range(80):
        mid = (lo + hi) / 2
        if avg_block_exposure(mid) < target:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2
    if abs(avg_block_exposure(k) - target) > tolerance_pp / 100:
        raise ValueError("vol-exposure calibration did not converge")
    return exposures_for(k)


def vol_target_strategy(rows: list[BacktestRow], target_exposure_pct: float,
                        cost_bps: float = 0.0) -> StrategyResult:
    """Exposure-matched, no-pillar volatility-targeting baseline."""
    exposures = calibrate_vol_exposures(rows, target_exposure_pct)
    label = f"Vol-target {target_exposure_pct:.0f}% (no pillars, matched benchmark)"
    return simulate_with_exposures(rows, exposures, label, cost_bps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_stats.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_stats.py test_backtest_stats.py
git commit -m "feat: add exposure-matched vol-targeting baseline"
```

---

### Task 4: Year-by-year table

**Files:**
- Modify: `backtest_stats.py`
- Modify: `test_backtest_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_backtest_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 test_backtest_stats.py`
Expected: FAIL with `AttributeError: ... no attribute 'yearly_table'`

- [ ] **Step 3: Implement in `backtest_stats.py`**

```python
class YearRow(TypedDict):
    year: str
    days: int
    mean_score: float
    timing_return_pct: float
    matched_return_pct: float
    vol_target_return_pct: float
    buy_hold_return_pct: float
    beat_benchmark: bool


def yearly_table(rows: list[BacktestRow], engage_min: float,
                 matched_fraction: float,
                 vol_exposures: list[float]) -> list[YearRow]:
    """Per-calendar-year strategy returns. matched_fraction and vol_exposures
    come from the FULL-SAMPLE calibration so year rows are comparable down
    the column. Block boundaries reset at each year start (approximation,
    disclosed in the report).
    """
    if len(vol_exposures) != len(rows):
        raise ValueError("vol_exposures must align with rows")
    out: list[YearRow] = []
    i = 0
    while i < len(rows):
        year = rows[i]["date"][:4]
        j = i
        while j < len(rows) and rows[j]["date"][:4] == year:
            j += 1
        chunk = rows[i:j]
        chunk_vol = vol_exposures[i:j]
        timing_exposures = [1.0 if r["total"] >= engage_min else 0.0 for r in chunk]
        timing = simulate_with_exposures(chunk, timing_exposures, "timing")
        matched = simulate_with_exposures(chunk, [matched_fraction] * len(chunk), "matched")
        vol = simulate_with_exposures(chunk, chunk_vol, "vol")
        buy_hold = simulate_with_exposures(chunk, [1.0] * len(chunk), "bh")
        out.append({
            "year": year,
            "days": len(chunk),
            "mean_score": _mean([r["total"] for r in chunk]),
            "timing_return_pct": timing["total_return_pct"],
            "matched_return_pct": matched["total_return_pct"],
            "vol_target_return_pct": vol["total_return_pct"],
            "buy_hold_return_pct": buy_hold["total_return_pct"],
            "beat_benchmark": timing["total_return_pct"] > matched["total_return_pct"],
        })
        i = j
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_stats.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_stats.py test_backtest_stats.py
git commit -m "feat: add year-by-year strategy comparison table"
```

---

### Task 5: Moving-block bootstrap CIs and the three statistics

**Files:**
- Modify: `backtest_stats.py`
- Modify: `test_backtest_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_backtest_stats.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 test_backtest_stats.py`
Expected: FAIL with `AttributeError: ... no attribute 'ic_statistic'`

- [ ] **Step 3: Implement in `backtest_stats.py`**

```python
def block_bootstrap_ci(rows: list[BacktestRow],
                       statistic: Callable[[list[BacktestRow]], float],
                       n_resamples: int = BOOTSTRAP_RESAMPLES,
                       block: int = BOOTSTRAP_BLOCK,
                       seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    """Moving-block bootstrap 95% CI: returns (point, ci_lo, ci_hi).

    Resamples contiguous blocks (with replacement) to preserve short-range
    autocorrelation from overlapping forward returns. Seeded -> deterministic.
    Resamples whose statistic is NaN (e.g. an empty decision band) are
    dropped from the percentile computation.
    """
    n = len(rows)
    if n < 2 * block:
        raise ValueError(f"Need at least {2 * block} rows for block bootstrap")
    point = statistic(rows)
    rng = random.Random(seed)
    n_blocks = math.ceil(n / block)
    max_start = n - block
    samples: list[float] = []
    for _ in range(n_resamples):
        resampled: list[BacktestRow] = []
        for _ in range(n_blocks):
            start = rng.randint(0, max_start)
            resampled.extend(rows[start:start + block])
        del resampled[n:]
        value = statistic(resampled)
        if not math.isnan(value):
            samples.append(value)
    if not samples:
        return (point, float("nan"), float("nan"))
    samples.sort()
    lo = samples[int(0.025 * (len(samples) - 1))]
    hi = samples[int(0.975 * (len(samples) - 1))]
    return (point, lo, hi)


def ic_statistic(horizon: int) -> Callable[[list[BacktestRow]], float]:
    """Spearman IC of total score vs forward return at the given horizon."""
    key = {1: "fwd1", 5: "fwd5", 20: "fwd20"}[horizon]
    def stat(rows: list[BacktestRow]) -> float:
        return spearman([r["total"] for r in rows], [r[key] for r in rows])
    return stat


def band_mean_statistic(band: str) -> Callable[[list[BacktestRow]], float]:
    """Mean 5-day forward return within one decision band (NaN if absent)."""
    def stat(rows: list[BacktestRow]) -> float:
        vals = [r["fwd5"] for r in rows if r["decision"] == band]
        return _mean(vals) if vals else float("nan")
    return stat


def decile_spread_statistic(rows: list[BacktestRow]) -> float:
    """Bottom-decile minus top-decile mean fwd5 - the contrarian-edge gate.

    Decile membership is recomputed on each (re)sample, so bootstrap CIs
    reflect ranking uncertainty too.
    """
    ranked = sorted(rows, key=lambda r: r["total"])
    tenth = len(ranked) // 10
    if tenth == 0:
        return float("nan")
    bottom = [r["fwd5"] for r in ranked[:tenth]]
    top = [r["fwd5"] for r in ranked[-tenth:]]
    return _mean(bottom) - _mean(top)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_stats.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_stats.py test_backtest_stats.py
git commit -m "feat: add moving-block bootstrap CIs for IC, band means, decile spread"
```

---

### Task 6: Vol-target row in strategy tables (index contract change)

`strategy_rows()` grows from 5 to 6 rows. New order: 0=constructive, 1=matched-constructive, 2=selective, 3=matched-selective, **4=vol-target (new)**, 5=buy & hold. Every index consumer is updated here: `build_report` headline indices and the three index-based tests in `test_backtest_report.py`.

**Files:**
- Modify: `backtest_report.py`
- Modify: `test_backtest_report.py`

- [ ] **Step 1: Write the failing test**

Append to `test_backtest_report.py` (inside `TestBacktestReport`):

```python
    def test_strategy_rows_include_vol_target_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        strats = backtest_report.strategy_rows(rows)
        self.assertEqual(len(strats), 6)
        self.assertIn("Vol-target", strats[4]["label"])
        self.assertEqual(strats[5]["label"], "Buy & hold")
        # Exposure-matched to the Score>=55 rule within calibration tolerance.
        self.assertAlmostEqual(
            strats[4]["exposure_pct"], strats[2]["exposure_pct"], delta=0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 test_backtest_report.py`
Expected: FAIL — `len(strats)` is 5, and the three existing index-based tests still reference index 4 as buy & hold (they will break in Step 3's refactor; updated below)

- [ ] **Step 3: Update `backtest_report.py`**

Add `vol_target_strategy` to the import from `backtest_stats`. Replace `strategy_rows` (`backtest_report.py:393-405`):

```python
def strategy_rows(rows: list[BacktestRow]) -> list[StrategyResult]:
    constructive = strategy(rows, f"Score >= {FULL_RISK_MIN} (CONSTRUCTIVE+)",
                            lambda r: r["total"] >= FULL_RISK_MIN)
    selective = strategy(rows, f"Score >= {ENGAGE_MIN} (SELECTIVE+)",
                         lambda r: r["total"] >= ENGAGE_MIN)
    buy_hold = strategy(rows, "Buy & hold", lambda r: True)
    return [
        constructive,
        _matched_exposure_strategy(rows, constructive),
        selective,
        _matched_exposure_strategy(rows, selective),
        vol_target_strategy(rows, selective["exposure_pct"]),
        buy_hold,
    ]
```

In `build_report`, update the index comment and unpacking (`backtest_report.py:434-437`):

```python
    # indices: 0=constructive, 1=matched-constructive, 2=selective,
    #          3=matched-selective, 4=vol-target, 5=buy&hold
    engage = headline_strategies[2]
    matched_engage = headline_strategies[3]
    vol_target = headline_strategies[4]
    buy_hold = headline_strategies[5]
```

Add one Executive Readout line right after the matched-baseline line:

```python
        f"- A no-pillar vol-target baseline at the same exposure returned "
        f"{_fmt_pct(vol_target['total_return_pct'], 1)} with {vol_target['sharpe']:.2f} Sharpe and "
        f"{_fmt_pct(vol_target['max_drawdown_pct'], 1)} max drawdown — the score must beat this "
        f"to justify the five-pillar machinery.",
```

- [ ] **Step 4: Update the three index-based tests in `test_backtest_report.py`**

In `test_matched_benchmark_sharpe_equals_buy_and_hold_sharpe`: change `strats[4]` to `strats[5]` and the index comment to the new 6-row order.
In `test_matched_benchmark_drawdown_shallower_than_full_buy_and_hold`: change `buy_hold_dd = strats[4][...]` to `strats[5][...]`.
(`test_cross_window_matched_fractions_differ` uses indices 2/3 only — no change.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 test_backtest_report.py && python3 test_backtest_stats.py`
Expected: both `OK`

- [ ] **Step 6: Commit**

```bash
git add backtest_report.py test_backtest_report.py
git commit -m "feat: add vol-target baseline row to strategy comparison tables"
```

---

### Task 7: Year-By-Year report section

**Files:**
- Modify: `backtest_report.py`
- Modify: `test_backtest_report.py`

- [ ] **Step 1: Write the failing test**

Append to `test_backtest_report.py`:

```python
    def test_report_contains_year_by_year_section(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)
            report = backtest_report.build_report(rows, "fixture.csv")

        self.assertIn("## Year-By-Year", report)
        self.assertIn("| 2024 |", report)
        self.assertIn("Beat benchmark", report)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 test_backtest_report.py`
Expected: FAIL with `'## Year-By-Year' not found`

- [ ] **Step 3: Implement the section in `backtest_report.py`**

Add `calibrate_vol_exposures` and `yearly_table` to the `backtest_stats` import. Add a section builder near the other helpers:

```python
def _year_section(rows: list[BacktestRow], selective: StrategyResult) -> list[str]:
    matched_fraction = selective["exposure_pct"] / 100.0
    vol_exposures = calibrate_vol_exposures(rows, selective["exposure_pct"])
    years = yearly_table(rows, ENGAGE_MIN, matched_fraction, vol_exposures)
    beats = sum(1 for y in years if y["beat_benchmark"])
    lines = [
        "",
        "## Year-By-Year",
        "",
        f"Calendar-year returns. Matched-benchmark fraction and vol-target calibration are "
        f"full-sample ({selective['exposure_pct']:.0f}% exposure), so rows are comparable down "
        "each column. Block boundaries reset at year start (approximation).",
        "",
        f"The Score >= {ENGAGE_MIN} rule beat its matched benchmark in "
        f"**{beats} of {len(years)} years**.",
        "",
        "| Year | Days | Mean Score | Score >= 55 | Matched Const. | Vol-Target | Buy & Hold | Beat benchmark? |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for y in years:
        lines.append(
            f"| {y['year']} | {y['days']:,} | {y['mean_score']:.0f} | "
            f"{_fmt_pct(y['timing_return_pct'], 1)} | {_fmt_pct(y['matched_return_pct'], 1)} | "
            f"{_fmt_pct(y['vol_target_return_pct'], 1)} | {_fmt_pct(y['buy_hold_return_pct'], 1)} | "
            f"{'✓' if y['beat_benchmark'] else '✗'} |"
        )
    return lines
```

In `build_report`, the full-sample selective result is `full_sample_strategies[2]`. After the validation strategy table block (after `backtest_report.py:565`), add:

```python
    lines.extend(_year_section(rows, full_sample_strategies[2]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_report.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_report.py test_backtest_report.py
git commit -m "feat: add year-by-year section to backtest report"
```

---

### Task 8: Statistical Significance report section

**Files:**
- Modify: `backtest_report.py`
- Modify: `test_backtest_report.py`

- [ ] **Step 1: Write the failing test**

The 30-row fixture is smaller than `2 * BOOTSTRAP_BLOCK` (42), so this test doubles it with year-shifted dates (60 rows) to exercise the full table rather than the too-small-sample fallback. Append to `test_backtest_report.py`:

```python
    def test_report_contains_significance_section(self):
        lines = FIXTURE_CSV.strip().split("\n")
        header, data = lines[0], lines[1:]
        shifted = [row.replace("2024-", "2025-", 1) for row in data]
        big_csv = "\n".join([header] + data + shifted) + "\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(big_csv, encoding="utf-8")
            rows = backtest_report.load_rows(path)
            report = backtest_report.build_report(rows, "fixture.csv")

        self.assertIn("## Statistical Significance", report)
        self.assertIn("95% CI", report)
        self.assertIn("Decile 1 - Decile 10", report)
        self.assertIn("zero excluded", report.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 test_backtest_report.py`
Expected: FAIL with `'## Statistical Significance' not found`

- [ ] **Step 3: Implement the section in `backtest_report.py`**

Add `block_bootstrap_ci`, `ic_statistic`, `band_mean_statistic`, `decile_spread_statistic` to the `backtest_stats` import. The 30-row test fixture is smaller than `2 * BOOTSTRAP_BLOCK` (42), so the section must degrade gracefully — that is what the `ValueError` guard handles.

```python
def _ci_row(label: str, point: float, lo: float, hi: float,
            fmt: Callable[[float], str]) -> str:
    if math.isnan(lo) or math.isnan(hi):
        return f"| {label} | {fmt(point)} | n/a | n/a |"
    excluded = "yes" if (lo > 0 or hi < 0) else "no"
    return f"| {label} | {fmt(point)} | [{fmt(lo)}, {fmt(hi)}] | {excluded} |"


def _significance_section(rows: list[BacktestRow]) -> list[str]:
    lines = [
        "",
        "## Statistical Significance",
        "",
        "Moving-block bootstrap (block 21 days, seeded, 95% CI). \"Zero excluded: no\" means",
        "the value is statistically indistinguishable from noise at this sample size.",
        "",
        "| Statistic | Point | 95% CI | Zero excluded |",
        "|---|---:|---:|:---:|",
    ]
    try:
        for horizon in HORIZONS:
            point, lo, hi = block_bootstrap_ci(rows, ic_statistic(horizon))
            lines.append(_ci_row(f"IC ({horizon}d)", point, lo, hi, _fmt_num))

        for band in DECISION_ORDER:
            if not any(r["decision"] == band for r in rows):
                continue
            point, lo, hi = block_bootstrap_ci(rows, band_mean_statistic(band))
            lines.append(_ci_row(f"Mean 5D, {band}", point, lo, hi, _fmt_pct))

        point, lo, hi = block_bootstrap_ci(rows, decile_spread_statistic)
        lines.append(_ci_row("Decile 1 - Decile 10 spread (5D)", point, lo, hi, _fmt_pct))
    except ValueError:
        lines.append("| (sample too small for block bootstrap) | n/a | n/a | n/a |")
    return lines
```

(`_fmt_pct` and `_fmt_num` both satisfy `Callable[[float], str]` via their default
`digits` argument.)

In `build_report`, immediately after the `_year_section` call:

```python
    lines.extend(_significance_section(rows))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_report.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_report.py test_backtest_report.py
git commit -m "feat: add bootstrap significance section to backtest report"
```

---

### Task 9: Transaction Cost Sensitivity report section

**Files:**
- Modify: `backtest_report.py`
- Modify: `test_backtest_report.py`

- [ ] **Step 1: Write the failing test**

Append to `test_backtest_report.py`:

```python
    def test_report_contains_cost_sensitivity_section(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)
            report = backtest_report.build_report(rows, "fixture.csv")

        self.assertIn("## Transaction Cost Sensitivity", report)
        self.assertIn("20 bps", report)
        self.assertIn("exposure flips", report)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 test_backtest_report.py`
Expected: FAIL with `'## Transaction Cost Sensitivity' not found`

- [ ] **Step 3: Implement the section in `backtest_report.py`**

Add `simulate_with_exposures` and `count_flips` to the `backtest_stats` import. Add module constant near `HORIZONS`:

```python
COST_LEVELS_BPS = (0.0, 5.0, 10.0, 20.0)
```

Section builder:

```python
def _cost_section(rows: list[BacktestRow], selective: StrategyResult) -> list[str]:
    timing_exposures = [1.0 if r["total"] >= ENGAGE_MIN else 0.0 for r in rows]
    matched_fraction = selective["exposure_pct"] / 100.0
    constant_exposures = [matched_fraction] * len(rows)
    vol_exposures = calibrate_vol_exposures(rows, selective["exposure_pct"])
    flips = count_flips(timing_exposures)
    lines = [
        "",
        "## Transaction Cost Sensitivity",
        "",
        "Costs are charged on each change in exposure (including initial entry):",
        "cost = |delta exposure| x bps / 10,000. The constant benchmark pays once at",
        "inception; the vol-target baseline pays on its smaller continuous adjustments.",
        "",
        f"The Score >= {ENGAGE_MIN} rule made **{flips} exposure flips** over this sample.",
        "",
        "| Strategy | 0 bps | 5 bps | 10 bps | 20 bps |",
        "|---|---:|---:|---:|---:|",
    ]
    variants = (
        (f"Score >= {ENGAGE_MIN} (SELECTIVE+)", timing_exposures),
        (f"Constant {selective['exposure_pct']:.0f}% SPY", constant_exposures),
        (f"Vol-target {selective['exposure_pct']:.0f}%", vol_exposures),
    )
    for label, exposures in variants:
        cells = []
        for bps in COST_LEVELS_BPS:
            result = simulate_with_exposures(rows, exposures, label, cost_bps=bps)
            sharpe = "n/a" if math.isnan(result["sharpe"]) else f"{result['sharpe']:.2f}"
            cells.append(f"{_fmt_pct(result['total_return_pct'], 1)} (S {sharpe})")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines
```

In `build_report`, after the `_significance_section` call:

```python
    lines.extend(_cost_section(rows, full_sample_strategies[2]))
```

Also add one Executive Readout line (after the vol-target line from Task 6), computed just above the `lines = [...]` literal:

```python
    timing_exposures = [1.0 if r["total"] >= ENGAGE_MIN else 0.0 for r in rows]
    flips = count_flips(timing_exposures)
    costed = simulate_with_exposures(
        rows, timing_exposures, "costed", cost_bps=10.0)
```

```python
        f"- At 10 bps per exposure change ({flips} flips), the full-sample Score >= {ENGAGE_MIN} "
        f"total return drops to {_fmt_pct(costed['total_return_pct'], 1)}.",
```

Finally, update the Limitations section: replace the bullet
`"- No trading costs, slippage, taxes, or execution delays.",` with:

```python
        "- Costs are modeled as linear bps on exposure changes only; no market impact, borrow, taxes, or execution delay.",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 test_backtest_report.py && python3 test_backtest_stats.py`
Expected: both `OK`

- [ ] **Step 5: Commit**

```bash
git add backtest_report.py test_backtest_report.py
git commit -m "feat: add transaction cost sensitivity section to backtest report"
```

---

### Task 10: Wire into CI, CLAUDE.md, and regenerate the live report

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `CLAUDE.md`
- Regenerate: `docs/backtest-report.md`

- [ ] **Step 1: Add the new module to CI**

In `.github/workflows/test.yml`:
- Line 26 (`py_compile`): append ` backtest_stats.py` to the file list.
- After the `test_backtest_report.py` step (lines 43-44), insert:

```yaml
      - name: Run backtest stats tests (test_backtest_stats.py)
        run: python test_backtest_stats.py
```

- Line 52 (mypy): change to `mypy models.py backtest_report.py backtest_stats.py --ignore-missing-imports --no-error-summary`

- [ ] **Step 2: Update CLAUDE.md test commands**

In the "Run all Python tests" command, insert `python3 test_backtest_stats.py && ` before `python3 test_analysis.py`. In the py_compile line, append ` backtest_stats.py`.

- [ ] **Step 3: Run mypy locally to catch type errors before CI**

Run: `python3 -m mypy models.py backtest_report.py backtest_stats.py --ignore-missing-imports --no-error-summary` (install with `pip install mypy` if missing; if pip install is not possible locally, note it and rely on CI)
Expected: no errors

- [ ] **Step 4: Run the full Python suite**

Run: `python3 test_fixes.py && python3 test_scoring.py && python3 test_data.py && python3 test_contracts.py && python3 test_backtest_report.py && python3 test_backtest_stats.py && python3 test_analysis.py && python3 test_smoke.py`
Expected: all `OK`

- [ ] **Step 5: Regenerate the live report and sanity-check runtime**

Run: `time python3 backtest_report.py`
Expected: `Backtest report written to docs/backtest-report.md`. If wall time exceeds ~2 minutes, lower `BOOTSTRAP_RESAMPLES` in `backtest_stats.py` to 1000 (spec allows this) and regenerate.

- [ ] **Step 6: Read the regenerated report and verify the new sections render sensibly**

Run: `grep -n "^## " docs/backtest-report.md`
Expected order includes: Year-By-Year, Statistical Significance, Transaction Cost Sensitivity. Open the file and check the year table covers 2005-2026 and CI rows show real intervals.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/test.yml CLAUDE.md docs/backtest-report.md backtest_stats.py
git commit -m "feat: regenerate backtest report with robustness analytics; wire CI"
```

---

### Task 11: Final review pass

- [ ] **Step 1: Re-run everything from a clean state**

Run: `python3 -m unittest discover 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 2: Check the diff against the spec**

Run: `git diff origin/main --stat`
Confirm: no changes to `backtest.py`, `server.py`, `scoring.py`, `static/`, or the CSV schema (spec's out-of-scope list).

- [ ] **Step 3: Verify report claims**

Read `docs/backtest-report.md` Executive Readout — confirm the vol-target line and the cost line state real numbers, and the year table's "beat benchmark" count matches its rows.

- [ ] **Step 4: Use superpowers:finishing-a-development-branch**

Implementation complete; decide merge/PR per that skill.
