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

def _mean(xs: Iterable[float]) -> float:
    vals = list(xs)
    return sum(vals) / len(vals) if vals else float("nan")


def _median(xs: Iterable[float]) -> float:
    vals = sorted(xs)
    if not vals:
        return float("nan")
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def _std(xs: Iterable[float]) -> float:
    vals = list(xs)
    if len(vals) < 2:
        return float("nan")
    avg = _mean(vals)
    return math.sqrt(sum((x - avg) ** 2 for x in vals) / (len(vals) - 1))


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 3:
        return float("nan")
    a = xs[:n]
    b = ys[:n]
    ma = _mean(a)
    mb = _mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return cov / math.sqrt(va * vb) if va and vb else float("nan")


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(_rank(xs), _rank(ys))


def max_drawdown(equity: list[float]) -> float:
    if not equity:
        return float("nan")
    peak = equity[0]
    mdd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            mdd = min(mdd, value / peak - 1)
    return mdd


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
    def stat(rows: list[BacktestRow]) -> float:
        if horizon == 1:
            fwds = [r["fwd1"] for r in rows]
        elif horizon == 5:
            fwds = [r["fwd5"] for r in rows]
        else:
            fwds = [r["fwd20"] for r in rows]
        return spearman([r["total"] for r in rows], fwds)
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
