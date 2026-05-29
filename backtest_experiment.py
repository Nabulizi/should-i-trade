"""
backtest_experiment.py — Can the score be re-weighted into real return signal?

Reads backtest_results.csv (produced by backtest.py) and tests whether a
data-driven recombination of the pillars beats the current hand-set weights.

Anti-overfit protocol
---------------------
Weights are derived ONLY from the TRAIN period (2005-2015) and every model is
scored ONLY on the held-out TEST period (2016-2026). If a model looks good in
train but not test, it's curve-fit and we say so.

Combiner: standardize each feature on train (z-score), weight each by its TRAIN
Spearman IC vs forward 5-day return, sum. IC-weighting auto-orients each
feature (a feature that predicts losses gets a negative weight) and introduces
no free per-feature parameters to overfit.

Models
  M0 baseline   = current composite `total`            (the live score)
  M1 inverted   = -total                               (mechanical "fade it")
  M2 pillars    = IC-weighted {vol,trend,breadth,mom,macro}
  M3 mean-rev   = IC-weighted {rsi2, dist20}
  M4 combined   = IC-weighted all 7 features

Run: python3 backtest_experiment.py   (after running backtest.py once)
"""
from __future__ import annotations
import csv
import math

import backtest as bt  # reuse spearman, _mean, _std, max_drawdown

TRAIN_END = "2016-01-01"     # train < this; test >= this
FEATURES = ["v", "tr", "br", "mo", "ma", "rsi2", "dist20"]
PILLARS = ["v", "tr", "br", "mo", "ma"]
MEANREV = ["rsi2", "dist20"]
TARGET = "fwd5"


def load():
    rows = []
    with open("backtest_results.csv") as f:
        for r in csv.DictReader(f):
            try:
                rec = {"date": r["date"], "total": float(r["total"]),
                       "fwd5": float(r["fwd5"]), "fwd20": float(r["fwd20"])}
                for k in FEATURES:
                    if r[k] == "":
                        raise ValueError
                    rec[k] = float(r[k])
                rows.append(rec)
            except (ValueError, KeyError):
                continue
    return rows


def standardizer(train, feat):
    xs = [r[feat] for r in train]
    mu, sd = bt._mean(xs), bt._std(xs)
    sd = sd if sd and sd > 0 else 1.0
    return mu, sd


def build_models(train, test):
    # train-period stats for standardization + IC weights
    stats = {f: standardizer(train, f) for f in FEATURES}
    def z(r, f):
        mu, sd = stats[f]
        return (r[f] - mu) / sd
    train_ic = {f: bt.spearman([r[f] for r in train], [r[TARGET] for r in train])
                for f in FEATURES}

    def ic_weighted(rows, feats):
        return [sum(train_ic[f] * z(r, f) for f in feats) for r in rows]

    models = {
        "M0 baseline (total)": ([r["total"] for r in train], [r["total"] for r in test]),
        "M1 inverted (-total)": ([-r["total"] for r in train], [-r["total"] for r in test]),
        "M2 IC-wt pillars": (ic_weighted(train, PILLARS), ic_weighted(test, PILLARS)),
        "M3 IC-wt mean-rev": (ic_weighted(train, MEANREV), ic_weighted(test, MEANREV)),
        "M4 IC-wt combined": (ic_weighted(train, FEATURES), ic_weighted(test, FEATURES)),
    }
    return models, train_ic


def strategy(test, signal, threshold):
    """Long SPY in non-overlapping 5d blocks when signal>threshold, else flat."""
    eq, curve, blocks, invested = 1.0, [1.0], [], 0
    i = 0
    while i < len(test):
        r, s = test[i], signal[i]
        inv = s > threshold
        ret = r["fwd5"] / 100 if inv else 0.0
        eq *= (1 + ret)
        curve.append(eq)
        blocks.append(ret)
        invested += 1 if inv else 0
        i += 5
    years = len(test) / 252.0
    cagr = (eq ** (1 / years) - 1) * 100 if years > 0 and eq > 0 else float("nan")
    mu, sd = bt._mean(blocks), bt._std(blocks)
    sharpe = (mu / sd * math.sqrt(252 / 5)) if sd and sd > 0 else float("nan")
    n_blocks = len(blocks)
    return {"totalRet": (eq - 1) * 100, "cagr": cagr, "sharpe": sharpe,
            "maxDD": bt.max_drawdown(curve) * 100,
            "expo": 100 * invested / n_blocks if n_blocks else 0}


def buy_hold(test):
    eq, curve, blocks = 1.0, [1.0], []
    i = 0
    while i < len(test):
        ret = test[i]["fwd5"] / 100
        eq *= (1 + ret); curve.append(eq); blocks.append(ret); i += 5
    years = len(test) / 252.0
    cagr = (eq ** (1 / years) - 1) * 100 if years > 0 and eq > 0 else float("nan")
    mu, sd = bt._mean(blocks), bt._std(blocks)
    sharpe = (mu / sd * math.sqrt(252 / 5)) if sd and sd > 0 else float("nan")
    return {"totalRet": (eq - 1) * 100, "cagr": cagr, "sharpe": sharpe,
            "maxDD": bt.max_drawdown(curve) * 100, "expo": 100.0}


def median(xs):
    s = sorted(xs); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    rows = load()
    train = [r for r in rows if r["date"] < TRAIN_END]
    test = [r for r in rows if r["date"] >= TRAIN_END]
    print("=" * 74)
    print("  RE-WEIGHTING EXPERIMENT — out-of-sample (train 2005-15, test 2016-26)")
    print("=" * 74)
    print(f"  train n={len(train)}  test n={len(test)}\n")

    models, train_ic = build_models(train, test)

    print("[A] TRAIN-PERIOD per-feature IC (used to set weights — sign/size):")
    for f in FEATURES:
        print(f"     {f:>7}: {train_ic[f]:+.3f}")

    print("\n[B] INFORMATION COEFFICIENT — train (in-sample) vs test (OUT-of-sample)")
    print("    A model is only real if TEST IC is positive & meaningful.")
    print(f"    {'model':<24} {'train IC':>9} {'test IC':>9}")
    test_signals = {}
    for name, (tr_sig, te_sig) in models.items():
        ic_tr = bt.spearman(tr_sig, [r[TARGET] for r in train])
        ic_te = bt.spearman(te_sig, [r[TARGET] for r in test])
        test_signals[name] = te_sig
        print(f"    {name:<24} {ic_tr:>+9.3f} {ic_te:>+9.3f}")

    print("\n[C] OUT-OF-SAMPLE STRATEGY (test 2016-26, long/flat, threshold = train median)")
    print(f"    {'model':<24} {'totRet%':>8} {'CAGR%':>7} {'Sharpe':>7} {'maxDD%':>7} {'expo%':>6}")
    for name, (tr_sig, te_sig) in models.items():
        thr = median(tr_sig)
        s = strategy(test, te_sig, thr)
        print(f"    {name:<24} {s['totalRet']:>+8.1f} {s['cagr']:>+7.2f} "
              f"{s['sharpe']:>7.2f} {s['maxDD']:>7.1f} {s['expo']:>5.0f}%")
    bh = buy_hold(test)
    print(f"    {'Buy & Hold':<24} {bh['totalRet']:>+8.1f} {bh['cagr']:>+7.2f} "
          f"{bh['sharpe']:>7.2f} {bh['maxDD']:>7.1f} {bh['expo']:>5.0f}%")


if __name__ == "__main__":
    main()
