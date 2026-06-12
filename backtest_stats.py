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
