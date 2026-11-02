#!/usr/bin/env python3
"""Does Classic's Execution Window predict what its labels claim? Exploratory.

Each row is tested against an outcome matching its label. Signals are read at the
close of day t, and outcomes start after t. All frozen before the first run, in
the commit that added this file:

  Breakouts working?     7+ sectors up.
    Outcome: sector closes at a new 20-day high on t+1 are higher 5 sessions later.
  Leaders holding?       SPY above its 20- and 50-day averages.
    Outcome: the top 3 sectors by 20-day return beat SPY over the next 5 sessions.
  Pullbacks bought?      RSP up on the day.
    Outcome: if SPY falls 0.5%+ on t+1, it is higher 5 sessions after that.
  Equal-weight leading?  RSP beat SPY on the day.
    Outcome: RSP beats SPY over the next 5 sessions.
  Follow-through?        Score 70+.
    Outcome: if SPY rose 0.5%+ on t, it is higher 5 sessions later.

  A row PASSES only if all three hold:
    1. Success rate is at least 5 points higher when the signal is on.
    2. The gap has the same sign in 2006-2015 and 2016-2026.
    3. The 95% block-bootstrap interval for the full-sample gap excludes zero.

  The panel earns a place on the new page only if at least 3 of 5 rows pass, or if
  it adds to the risk line: within at least 2 of the 3 risk levels (each group
  100+ days), days with 4-5 rows on have a 10%+ SPY drop rate at least 5 points
  below days with 0-1 rows on, within the next 63 sessions.

Daily samples overlap. Five rows are tested with no multiple-testing correction,
so one marginal pass means little.

  python3 backtest_execution_window.py

Stdlib only. Network on first run (Yahoo, cached by backtest.py).
"""

import random
import statistics as st

import backtest as b
import scoring

H = 5
DROP_H = 63
DROP = -0.10
BLOCK = 21
RESAMPLES = 2000
START = "2006-01-01"
MID = "2016-01-01"
ROWS = ("Breakouts working?", "Leaders holding?", "Pullbacks bought?",
        "Equal-weight leading?", "Follow-through?")


def main():
    dates, al = b.align(b.load_all())
    spy, rsp, sectors = al["SPY"], al["RSP"], {s: al[s] for s in b.SECTORS}

    def ma(series, i, n):
        window = [x for x in series[i - n + 1:i + 1] if x]
        return sum(window) / len(window) if len(window) >= n * 0.75 else None

    def ret(series, i, j):
        return series[j] / series[i] - 1 if series[i] and series[j] else None

    def vol20(i):
        c = [x for x in spy[i - 20:i + 1] if x]
        return st.stdev(c[k + 1] / c[k] - 1 for k in range(20)) * 252 ** 0.5 * 100 if len(c) == 21 else None

    def max_drop(i):
        peak, worst = spy[i], 0
        for p in spy[i:i + DROP_H + 1]:
            if p:
                peak = max(peak, p)
                worst = min(worst, p / peak - 1)
        return worst

    obs = {row: [] for row in ROWS}   # (day index in sample, signal on, successes, trials)
    counts = []
    for i in range(b.WARMUP, len(dates) - max(H + 2, DROP_H + 1)):
        if dates[i] < START or not (spy[i] and rsp[i] and spy[i - 1] and rsp[i - 1]):
            continue
        scored = b.score_day(i, al)
        ma20, ma50 = ma(spy, i, 20), ma(spy, i, 50)
        if not (scored and ma20 and ma50):
            continue
        day = dates[i]
        sectors_up = sum(1 for s in sectors.values() if s[i] and s[i - 1] and s[i] > s[i - 1])
        spy_chg, rsp_chg = ret(spy, i - 1, i), ret(rsp, i - 1, i)
        on = dict(zip(ROWS, (sectors_up >= 7, spy[i] > ma20 and spy[i] > ma50, rsp_chg >= 0,
                             rsp_chg > spy_chg, scored["total"] >= 70)))

        hits = trials = 0
        for s in sectors.values():
            prior = [x for x in s[i - 19:i + 1] if x]
            if len(prior) == 20 and s[i + 1] and s[i + 6] and s[i + 1] > max(prior):
                trials += 1
                hits += s[i + 6] > s[i + 1]
        if trials:
            obs["Breakouts working?"].append((day, on["Breakouts working?"], hits, trials))

        ranked = sorted(((ret(s, i - 20, i), s) for s in sectors.values()
                         if ret(s, i - 20, i) is not None and s[i + H]), key=lambda x: x[0], reverse=True)[:3]
        if len(ranked) == 3:
            leaders = st.mean(ret(s, i, i + H) for _, s in ranked)
            obs["Leaders holding?"].append((day, on["Leaders holding?"], int(leaders > ret(spy, i, i + H)), 1))

        if ret(spy, i, i + 1) <= -0.005:
            obs["Pullbacks bought?"].append((day, on["Pullbacks bought?"], int(spy[i + 6] > spy[i + 1]), 1))

        obs["Equal-weight leading?"].append(
            (day, on["Equal-weight leading?"], int(ret(rsp, i, i + H) > ret(spy, i, i + H)), 1))

        if spy_chg >= 0.005:
            obs["Follow-through?"].append((day, on["Follow-through?"], int(spy[i + H] > spy[i]), 1))

        hyg_ma = ma(al["HYG"], i, 50)
        if al["HYG"][i] and hyg_ma and vol20(i) is not None:
            level = scoring.risk_level(vol20(i), spy[i] < ma50, al["HYG"][i] < hyg_ma * 0.998)["level"]
            counts.append((day, level, sum(on.values()), max_drop(i) < DROP))

    def rate(rows):
        trials = sum(r[3] for r in rows)
        return sum(r[2] for r in rows) / trials if trials else float("nan")

    def gap(rows):
        return rate([r for r in rows if r[1]]) - rate([r for r in rows if not r[1]])

    rng = random.Random("EXECWINDOW")
    passed = 0
    print(f"{'Row':24}{'on':>7}{'off':>7}{'gap':>7}{'95% interval':>18}{'2006-15':>9}{'2016-26':>9}  result")
    for row in ROWS:
        rows = obs[row]
        early = [r for r in rows if r[0] < MID]
        late = [r for r in rows if r[0] >= MID]
        boots = []
        for _ in range(RESAMPLES):
            sample = []
            while len(sample) < len(rows):
                k = rng.randrange(max(1, len(rows) - BLOCK))
                sample += rows[k:k + BLOCK]
            g = gap(sample[:len(rows)])
            if g == g:
                boots.append(g)
        boots.sort()
        lo, hi = boots[int(len(boots) * .025)], boots[int(len(boots) * .975)]
        full, g1, g2 = gap(rows), gap(early), gap(late)
        ok = full >= .05 and g1 * g2 > 0 and lo > 0
        passed += ok
        on_rows = [r for r in rows if r[1]]
        print(f"{row:24}{rate(on_rows):7.0%}{rate([r for r in rows if not r[1]]):7.0%}{full * 100:+6.1f}p"
              f"{f'[{lo * 100:+.1f}, {hi * 100:+.1f}]':>18}{g1 * 100:+8.1f}p{g2 * 100:+8.1f}p  {'PASS' if ok else 'FAIL'}"
              f"  (n={sum(r[3] for r in rows)})")

    print(f"\nRows passed: {passed} of {len(ROWS)}")
    print("\n10%+ SPY drop within 63 sessions, by rows on, within each risk level")
    print(f"{'Level':10}{'0-1 on':>16}{'2-3 on':>16}{'4-5 on':>16}{'adds?':>8}")
    adds = 0
    for level in ("Normal", "Elevated", "High"):
        group = [c for c in counts if c[1] == level]
        cells = [[c for c in group if lo <= c[2] <= hi] for lo, hi in ((0, 1), (2, 3), (4, 5))]
        text = [f"{sum(c[3] for c in x) / len(x):.0%} (n={len(x)})" if x else "-" for x in cells]
        ok = len(cells[0]) >= 100 and len(cells[2]) >= 100 and (
            sum(c[3] for c in cells[0]) / len(cells[0]) - sum(c[3] for c in cells[2]) / len(cells[2]) >= .05)
        adds += ok
        print(f"{level:10}{text[0]:>16}{text[1]:>16}{text[2]:>16}{'yes' if ok else 'no':>8}")
    print(f"\nVERDICT: {'PASS' if passed >= 3 or adds >= 2 else 'FAIL'} (rows passed {passed}, risk levels added {adds})")


if __name__ == "__main__":
    main()
