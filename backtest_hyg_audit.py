#!/usr/bin/env python3
"""P2-021: audit of the Macro pillar's HYG 50-day rule. Research only.

The rule adds 8 points above 1.002x the 50-day average and removes 10 below
0.998x. The live average uses adjusted closes (data.yf_history), so distributions
don't flip it, and this audit uses adjusted closes too. It measures how the rule
behaves and changes nothing: any change to the rule is a versioned model change
(D-006).

  python3 backtest_hyg_audit.py

Stdlib only. Network: Yahoo and FRED.
"""

import bisect
import csv
import io
import json
import statistics as st
import urllib.request
from datetime import date, datetime, timezone

import data

HORIZON = 63
DROP = -0.10
BAND = 0.002


def chart(symbol):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           "?interval=1d&period1=1104537600&period2=4102444800")
    result = json.loads(data.fetch_url(url, timeout=30))["chart"]["result"][0]
    bars = [(datetime.fromtimestamp(t, tz=timezone.utc).date(), a) for t, a in
            zip(result["timestamp"], result["indicators"]["adjclose"][0]["adjclose"]) if a]
    gaps = [(y[0] - x[0]).days for x, y in zip(bars, bars[1:])]
    assert len(bars) > 4000 and st.median(gaps) == 1, f"{symbol} history is not daily"
    return [b[0] for b in bars], [b[1] for b in bars]


def fred(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=2005-01-01"
    req = urllib.request.Request(url, headers={"User-Agent": data._FRED_UA})
    body = urllib.request.urlopen(req, timeout=60).read().decode()
    return [(date.fromisoformat(d), float(v))
            for d, v in list(csv.reader(io.StringIO(body)))[1:] if v not in ("", ".")]


def states(closes, band=BAND):
    """{index: (state, distance from the 50-day average)}, as the live rule classifies."""
    out = {}
    for i in range(49, len(closes)):
        ratio = closes[i] / (sum(closes[i - 49:i + 1]) / 50)
        out[i] = ("Above" if ratio > 1 + band else "Below" if ratio < 1 - band else "Near", ratio - 1)
    return out


def main():
    dates, hyg = chart("HYG")
    spy_dates, spy = chart("SPY")
    print(f"HYG {dates[0]} to {dates[-1]}")

    def outcome(i):
        k = bisect.bisect_right(spy_dates, dates[i]) - 1
        if k + HORIZON >= len(spy):
            return None
        peak, worst = spy[k], 0
        for p in spy[k:k + HORIZON + 1]:
            peak = max(peak, p)
            worst = min(worst, p / peak - 1)
        return spy[k + HORIZON] / spy[k] - 1, worst

    def line(label, idx):
        res = [o for o in (outcome(i) for i in idx) if o]
        print(f"{label:26}{len(res):6d}{st.mean(o[0] for o in res):9.1%}"
              f"{sum(o[1] < DROP for o in res) / len(res):14.0%}")

    rows = states(hyg)
    print(f"\n{'Label':26}{'days':>6}{'3m SPY':>9}{'P(10%+ drop)':>14}")
    for state in ("Above", "Near", "Below"):
        line(state, [i for i, r in rows.items() if r[0] == state])
    line("All", list(rows))

    for label, lo, hi in (("2007-2015", date(2007, 1, 1), date(2016, 1, 1)),
                          ("2016-2026", date(2016, 1, 1), date(2100, 1, 1))):
        print(f"\n{label}")
        for state in ("Above", "Below"):
            line(state, [i for i, r in rows.items() if r[0] == state and lo <= dates[i] < hi])
        line("All", [i for i in rows if lo <= dates[i] < hi])

    # Does the rule add anything beyond SPY's own trend, which the Trend pillar already scores?
    spy_rows = states(spy)
    spy_idx = {d: i for i, d in enumerate(spy_dates)}
    spy_state = {i: spy_rows.get(spy_idx.get(dates[i]), (None,))[0] for i in rows}
    agree = sum(spy_state[i] == rows[i][0] for i in rows if spy_state[i]) / len(rows)
    print(f"\nHYG and SPY share a label on {agree:.0%} of days")
    for spy_s in ("Above", "Below"):
        for hyg_s in ("Above", "Below"):
            line(f"SPY {spy_s}, HYG {hyg_s}", [i for i, r in rows.items()
                                                if r[0] == hyg_s and spy_state[i] == spy_s])

    print("\nBand width sensitivity (not a fit)")
    print(f"{'band':>7}{'changes/yr':>12}{'Below share':>13}{'P(drop) Below':>15}")
    for band in (0.002, 0.005, 0.01, 0.02):
        r = states(hyg, band)
        order = sorted(r)
        flips = sum(r[a][0] != r[b][0] for a, b in zip(order, order[1:]))
        below = [i for i in r if r[i][0] == "Below"]
        res = [o for o in (outcome(i) for i in below) if o]
        print(f"{band:7.1%}{flips / (len(r) / 252):12.0f}{len(below) / len(r):13.0%}"
              f"{sum(o[1] < DROP for o in res) / len(res):15.0%}")
    below = [r for r in rows.values() if r[0] == "Below"]
    print(f"Below days within 1% of the average: {sum(r[1] > -0.01 for r in below) / len(below):.0%}")

    # Is the label tracking credit stress? The real HY spread only exists since Oct 2023.
    hy = fred("BAMLH0A0HYM2")
    hy_days = [d for d, _ in hy]
    print("\nHY spread by label (Oct 2023 on)")
    for state in ("Above", "Near", "Below"):
        vals = [hy[bisect.bisect_right(hy_days, dates[i]) - 1][1] for i, r in rows.items()
                if r[0] == state and dates[i] >= hy_days[0]]
        print(f"  {state:6} days {len(vals):4d}  median {st.median(vals):.2f}  max {max(vals):.2f}")
    baa = fred("BAA10Y")
    baa_days = [d for d, _ in baa]
    print("BAA10Y by label (full history)")
    for state in ("Above", "Near", "Below"):
        vals = [baa[bisect.bisect_right(baa_days, dates[i]) - 1][1] for i, r in rows.items() if r[0] == state]
        print(f"  {state:6} days {len(vals):4d}  median {st.median(vals):.2f}")


if __name__ == "__main__":
    main()
