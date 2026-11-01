#!/usr/bin/env python3
"""Exploratory replay of the liquidity panel rule against SPY outcomes.

Source of the historical figures on the liquidity card. One pass, NOT
preregistered, and not a validated signal. Limits:
  - today's revised FRED data, approximating lag by reading signals 7 days old
  - BAA10Y stands in for the HY spread (FRED serves HY only from Oct 2023)
  - deadbands and votes as shipped in data.py; nothing fitted to these outcomes

  python3 backtest_liquidity.py

Stdlib only. Network: FRED and Yahoo.
"""

import bisect
import csv
import io
import json
import statistics as st
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import data

HORIZON = 63          # trading days, about 3 months
DROP = -0.10          # peak-to-trough within the horizon
VOL_WINDOW = 20
IDS = ["WALCL", "WTREGEN", "RRPONTSYD", "DFII10", "DGS2", "DTWEXBGS", "BAA10Y", "NFCI"]


def fred(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=2003-01-01"
    req = urllib.request.Request(url, headers={"User-Agent": data._FRED_UA})
    body = urllib.request.urlopen(req, timeout=60).read().decode()
    return [(date.fromisoformat(d), float(v))
            for d, v in list(csv.reader(io.StringIO(body)))[1:] if v not in ("", ".")]


def as_of(series, day):
    i = bisect.bisect_right([d for d, _ in series], day) - 1
    return series[i][1] if i >= 0 else None


def spy_daily():
    # range=max silently returns monthly bars; explicit periods return daily.
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/SPY"
           "?interval=1d&period1=1104537600&period2=4102444800")
    chart = json.loads(data.fetch_url(url, timeout=30))["chart"]["result"][0]
    bars = [(datetime.fromtimestamp(t, tz=timezone.utc).date(), a)
            for t, a in zip(chart["timestamp"], chart["indicators"]["adjclose"][0]["adjclose"]) if a]
    gaps = [(b[0] - a[0]).days for a, b in zip(bars, bars[1:])]
    assert len(bars) > 5000 and st.median(gaps) == 1, "SPY history is not daily"
    return [b[0] for b in bars], [b[1] for b in bars]


def main():
    with ThreadPoolExecutor(len(IDS)) as ex:
        s = dict(zip(IDS, ex.map(fred, IDS)))
    net = data._net_liquidity(s["WALCL"], s["WTREGEN"], s["RRPONTSYD"])
    rules = [("net_liquidity", net, data._NET_LIQUIDITY_DEADBAND, True, 1),
             ("real_yield", s["DFII10"], 0.10, False, 0.5),
             ("two_year", s["DGS2"], 0.10, False, 0.5),
             ("dollar", s["DTWEXBGS"], 1.0, False, 1),
             ("credit", s["BAA10Y"], 0.25, False, 1),
             ("nfci", s["NFCI"], 0.05, False, 1)]

    def votes(day):
        total = 0
        for _, series, deadband, higher_loosens, weight in rules:
            a = as_of(series, day - timedelta(days=7))
            b = as_of(series, day - timedelta(days=35))
            if a is None or b is None:
                return None
            change = round(a - b, 4)
            if abs(change) >= deadband:
                total += weight if (change > 0) == higher_loosens else -weight
        return total

    dates, px = spy_daily()

    def max_drop(i):
        peak, worst = px[i], 0
        for p in px[i:i + HORIZON + 1]:
            peak = max(peak, p)
            worst = min(worst, p / peak - 1)
        return worst

    def trailing_vol(i):
        r = [px[k + 1] / px[k] - 1 for k in range(i - VOL_WINDOW, i)]
        return st.stdev(r) * 252 ** 0.5 * 100

    rows, day = [], date(2006, 3, 1)
    while day <= dates[-1]:
        v, i = votes(day), bisect.bisect_right(dates, day) - 1
        if v is not None and i + HORIZON < len(px):
            tone = "Loosening" if v >= 2 else "Tightening" if v <= -2 else "Neutral"
            rows.append((tone, px[i + HORIZON] / px[i] - 1, max_drop(i), trailing_vol(i)))
        day += timedelta(days=7)
    assert len(rows) > 1000, "too few weeks"

    def report(label, group):
        drops = sum(r[2] < DROP for r in group) / len(group)
        print(f"{label:24}{len(group):6d}{st.mean(r[1] for r in group):9.1%}{drops:10.0%}")

    print(f"{'Weeks ' + str(len(rows)):24}{'n':>6}{'3m mean':>9}{'P(10%+)':>10}")
    for tone in ("Loosening", "Neutral", "Tightening"):
        report(tone, [r for r in rows if r[0] == tone])
    report("All weeks", rows)
    cutoff = st.median(r[3] for r in rows)
    print(f"\nMedian trailing {VOL_WINDOW}d vol: {cutoff:.1f}%")
    for tone in ("Loosening", "Neutral", "Tightening"):
        report(f"{tone}, vol >= median", [r for r in rows if r[0] == tone and r[3] >= cutoff])
        report(f"{tone}, vol < median", [r for r in rows if r[0] == tone and r[3] < cutoff])


if __name__ == "__main__":
    main()
