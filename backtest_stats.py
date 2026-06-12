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
