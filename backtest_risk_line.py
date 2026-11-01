#!/usr/bin/env python3
"""Replay of the "Risk today" line (scoring.risk_level). Exploratory, one pass.

Frozen before the first run, in the commit that added this file:

  Flags: SPY 20-day realized vol >= 13.2%; SPY below its 50-day average;
         HYG more than 0.2% below its 50-day average.
  Levels: 0 flags Normal, 1-2 Elevated, 3 High.
  Outcome: SPY 10%+ peak-to-trough drop within the next 63 trading days.

  Passes only if all three hold:
    1. Drop rate rises Normal < Elevated < High, full sample and in both 2007-2015
       and 2016-2026.
    2. Fewer label changes per year than the score's five bands.
    3. High minus Normal drop rate is at least RISK-OFF minus RISK-ON.

If it fails, the page must not lead with these labels. Daily samples overlap, so
differences are descriptive, not significance tests. The 13.2% cutoff came from
an earlier replay on this same history, so this is not out of sample.

  python3 backtest_risk_line.py

Stdlib only. Network on first run (Yahoo, cached by backtest.py).
"""

import statistics as st

import backtest as b
import scoring

HORIZON = 63
DROP = -0.10
LEVELS = ("Normal", "Elevated", "High")
BANDS = ("RISK-ON", "CONSTRUCTIVE", "SELECTIVE", "DE-RISK", "RISK-OFF")
PERIODS = (("Full", "0000", "9999"), ("2007-2015", "2007", "2016"), ("2016-2026", "2016", "9999"))


def band(total):
    return ("RISK-ON" if total >= 85 else "CONSTRUCTIVE" if total >= 70 else
            "SELECTIVE" if total >= 55 else "DE-RISK" if total >= 40 else "RISK-OFF")


def main():
    dates, al = b.align(b.load_all())
    spy, hyg = al["SPY"], al["HYG"]

    def ma50(series, i):
        window = [x for x in series[i - 49:i + 1] if x]
        return sum(window) / len(window) if len(window) >= 38 else None

    def vol20(i):
        c = [x for x in spy[i - 20:i + 1] if x]
        if len(c) < 21:
            return None
        return st.stdev(c[k + 1] / c[k] - 1 for k in range(20)) * 252 ** 0.5 * 100

    def drop_within(i):
        peak, worst = spy[i], 0
        for p in spy[i:i + HORIZON + 1]:
            if p:
                peak = max(peak, p)
                worst = min(worst, p / peak - 1)
        return worst

    rows = []
    for i in range(b.WARMUP, len(dates) - HORIZON):
        if dates[i] < b.ANALYSIS_START or not spy[i] or not hyg[i]:
            continue
        spy_ma, hyg_ma = ma50(spy, i), ma50(hyg, i)
        scored = b.score_day(i, al)
        if not (scored and spy_ma and hyg_ma):
            continue
        read = scoring.risk_level(vol20(i), spy[i] < spy_ma, hyg[i] < hyg_ma * 0.998)
        rows.append((dates[i], read["level"], band(scored["raw_total"]), drop_within(i) < DROP,
                     vol20(i + 21) if i + 21 < len(spy) else None))
    print(f"{len(rows)} days, {rows[0][0]} to {rows[-1][0]}\n")

    def rate(group):
        return sum(r[3] for r in group) / len(group) if group else float("nan")

    rates = {}
    for name, lo, hi in PERIODS:
        sample = [r for r in rows if lo <= r[0][:4] < hi]
        print(f"{name}: share of days, P(10%+ drop), next-month vol")
        for label in LEVELS:
            group = [r for r in sample if r[1] == label]
            vols = [r[4] for r in group if r[4] is not None]
            rates[name, label] = rate(group)
            print(f"  {label:13}{len(group) / len(sample):6.0%}{rate(group):8.0%}{st.mean(vols):8.1f}%")
        for label in BANDS:
            group = [r for r in sample if r[2] == label]
            rates[name, label] = rate(group)
            print(f"  {label:13}{len(group) / len(sample):6.0%}{rate(group):8.0%}")
        print(f"  {'All':13}{'':6}{rate(sample):8.0%}\n")

    years = len(rows) / 252
    level_changes = sum(x[1] != y[1] for x, y in zip(rows, rows[1:])) / years
    band_changes = sum(x[2] != y[2] for x, y in zip(rows, rows[1:])) / years
    gap_level = rates["Full", "High"] - rates["Full", "Normal"]
    gap_band = rates["Full", "RISK-OFF"] - rates["Full", "RISK-ON"]
    print(f"Label changes a year: risk line {level_changes:.0f}, score bands {band_changes:.0f}")
    print(f"Drop-rate gap: High-Normal {gap_level:.0%}, RISK-OFF minus RISK-ON {gap_band:.0%}\n")

    rising = all(rates[p[0], "Normal"] < rates[p[0], "Elevated"] < rates[p[0], "High"] for p in PERIODS)
    fewer = level_changes < band_changes
    wider = gap_level >= gap_band
    print(f"1. Drop rate rises in every period: {'PASS' if rising else 'FAIL'}")
    print(f"2. Fewer changes than score bands:  {'PASS' if fewer else 'FAIL'}")
    print(f"3. Separates at least as well:      {'PASS' if wider else 'FAIL'}")
    print(f"VERDICT: {'PASS' if rising and fewer and wider else 'FAIL'}")


if __name__ == "__main__":
    main()
