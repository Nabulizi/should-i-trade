#!/usr/bin/env python3
"""QR-010: Market Quality Score as a forward-volatility gauge.

Preregistration: quant-research/docs/preregistrations/QR-010-mqs-volatility.md
(one primary criterion, frozen before the full run). This script implements
exactly that spec on the existing replay engine. RISK-ranking claim only;
the return-timing claims were falsified by backtest.py and stay falsified.

  python3 backtest_vol.py --smoke   # machinery check (counts only, 2005-2006)
  python3 backtest_vol.py           # the single frozen full run

Stdlib only. Deterministic (permutation seed "QR010").
"""

import math
import random
import sys

from backtest import (ALL_SYMBOLS, ANALYSIS_START, WARMUP,
                      _pearson, _rank, align, load_all, score_day)

H = 21             # primary forward horizon, trading days
H5 = 5             # robustness horizon
STRIDE = 21        # non-overlapping blocks: every 21st scored day
PERMS = 100_000    # permutation test draws
SEED = "QR010"
SUBPERIODS = [("2005-2010", "2005", "2010"), ("2011-2015", "2011", "2015"),
              ("2016-2019", "2016", "2019"), ("2020-2026", "2020", "2026")]


def _std(xs):
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _rv(returns):
    """Annualized realized vol (%) from daily simple returns."""
    return _std(returns) * math.sqrt(252) * 100


def _dd(closes):
    peak, worst = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        worst = min(worst, c / peak - 1)
    return worst * 100


def build_rows(smoke=False):
    raw = load_all()
    master, aligned = align(raw)
    for s in ALL_SYMBOLS:
        aligned.setdefault(s, [None] * len(master))
    spy, vix = aligned["SPY"], aligned["^VIX"]
    n = len(master)
    rows = []
    for i in range(WARMUP, n - H):
        if master[i] < ANALYSIS_START:
            continue
        if smoke and master[i] >= "2007-01-01":
            break
        window = spy[i - H - 1: i + H + 1]
        if any(v is None for v in window):
            continue
        s = score_day(i, aligned)
        if s is None:
            continue
        fwd = [spy[j] / spy[j - 1] - 1 for j in range(i + 1, i + H + 1)]
        trail = [spy[j] / spy[j - 1] - 1 for j in range(i - H + 1, i + 1)]
        rows.append({
            "date": master[i], "score": s["total"],
            "rv21": _rv(fwd), "rv5": _rv(fwd[:H5]),
            "worst": min(fwd) * 100, "dd": _dd(spy[i: i + H + 1]),
            "vix": vix[i], "trail_rv": _rv(trail),
        })
    return rows


def spearman_p(a, b):
    """Spearman rho and two-sided permutation p (ranks fixed, one re-ranked)."""
    ra, rb = _rank(a), _rank(b)
    rho = _pearson(ra, rb)
    rng = random.Random(SEED)
    hits = 0
    perm = rb[:]
    for _ in range(PERMS):
        rng.shuffle(perm)
        if abs(_pearson(ra, perm)) >= abs(rho):
            hits += 1
    return rho, hits / PERMS


def rho_only(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    return _pearson(_rank([p[0] for p in pairs]), _rank([p[1] for p in pairs]))


def quintiles(blocks, key):
    ordered = sorted(blocks, key=lambda r: r["score"])
    k = len(ordered) // 5
    qs = [ordered[j * k:(j + 1) * k if j < 4 else len(ordered)] for j in range(5)]
    return [sum(r[key] for r in q) / len(q) for q in qs]


def main():
    smoke = "--smoke" in sys.argv
    rows = build_rows(smoke=smoke)
    blocks = rows[::STRIDE]
    if smoke:
        nn = sum(1 for r in rows if r["vix"] is not None)
        print(f"SMOKE ok: rows={len(rows)} blocks={len(blocks)} "
              f"vix_nonnull={nn} first={rows[0]['date']} last={rows[-1]['date']}")
        print("fields:", {k: round(v, 3) if isinstance(v, float) else v
                          for k, v in rows[0].items()})
        return

    scores = [r["score"] for r in blocks]
    rv = [r["rv21"] for r in blocks]
    rho, p = spearman_p(scores, rv)
    q = quintiles(blocks, "rv21")
    primary = rho < 0 and p < 0.01 and q[0] > q[4]
    print(f"QR-010 blocks={len(blocks)} ({blocks[0]['date']} .. {blocks[-1]['date']})")
    print(f"PRIMARY: rho(score,RV21)={rho:.3f} p={p:.5f} "
          f"bottomQ={q[0]:.1f}% topQ={q[4]:.1f}% -> "
          f"{'PASS' if primary else 'FAIL'}")
    print(f"quintile mean RV21 (low->high score): "
          + " ".join(f"{v:.1f}" for v in q))

    rho5, p5 = spearman_p(scores, [r["rv5"] for r in blocks])
    q5 = quintiles(blocks, "rv5")
    print(f"RV5: rho={rho5:.3f} p={p5:.5f} bottomQ={q5[0]:.1f}% topQ={q5[4]:.1f}%")
    print(f"tails: rho(score,worst-day)={rho_only(scores, [r['worst'] for r in blocks]):.3f} "
          f"rho(score,drawdown)={rho_only(scores, [r['dd'] for r in blocks]):.3f} "
          f"(positive = higher score, milder tail)")
    print(f"overlapping view (all {len(rows)} days, no p): "
          f"rho={rho_only([r['score'] for r in rows], [r['rv21'] for r in rows]):.3f}")

    for label, lo, hi in SUBPERIODS:
        sub = [r for r in blocks if lo <= r["date"][:4] <= hi]
        print(f"subperiod {label}: n={len(sub)} "
              f"rho={rho_only([r['score'] for r in sub], [r['rv21'] for r in sub]):.3f}")

    rho_vix = rho_only([r["vix"] for r in blocks], rv)
    rho_trv = rho_only([r["trail_rv"] for r in blocks], rv)
    beats = abs(rho) > abs(rho_vix) and abs(rho) > abs(rho_trv)
    print(f"BASELINES: rho(VIX,RV21)={rho_vix:.3f} rho(trailRV,RV21)={rho_trv:.3f}")
    print("WORDING GATE: " + ("score adds information beyond trivial predictors"
          if beats else "consistent with known volatility persistence; no added "
          "information beyond VIX/trailing RV demonstrated"))


if __name__ == "__main__":
    main()
