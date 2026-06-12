"""
backtest.py — Does the Market Quality Score actually predict forward returns?

Walk-forward replay of the live 5-pillar engine over historical data.

Method
------
1. Download ~6y of *adjusted* daily closes for every symbol the pillars need
   (one Yahoo call per symbol, cached to .backtest_cache/).
2. For each historical trading day T (after a 210-day warmup), reconstruct the
   exact inputs the live engine sees — a `quotes` dict (price + that day's
   change %) and trailing `histories` — using ONLY data through T's close.
   Then call the real scoring.score_* functions and aggregate with the live
   PILLAR_WEIGHTS, and apply the same VIX / below-200d safety overrides.
3. Measure SPY forward returns from T's close to T+1 / T+5 / T+20 close.
4. Test whether higher scores → higher / better risk-adjusted forward returns.

No look-ahead: the score on day T uses data up to T's close; the trade is
entered at T's close and exited k days later. This mirrors a pre-session
decision made the evening of day T.

Honest scope note
-----------------
The date-deterministic overlays (FOMC / OpEx / seasonality) are NEUTRALIZED in
this replay — their code uses datetime.now() and the FOMC table only covers
2026-27, and they are small, deterministic adjustments, not the hypothesis
under test. The market-data pillars (volatility/trend/breadth/momentum/macro
ex-calendar) AND the VIX/below-200d safety overrides are replayed faithfully.

Stdlib only. Run: python3 backtest.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

import scoring
from config import PILLAR_WEIGHTS

CACHE_DIR = ".backtest_cache"
# NOTE: Yahoo's range=max silently downgrades interval=1d to MONTHLY bars.
# We force true daily granularity with explicit period1/period2 timestamps.
DOWNLOAD_START = "2003-01-01"  # gives 252-bar warmup before ANALYSIS_START
ANALYSIS_START = "2005-01-01"  # first scored day (RSP/sectors exist; covers 2008+)
WINDOW = 252           # trailing bars fed to each pillar — matches the LIVE engine,
                       # which only fetches ~220-252 bars, and keeps replay O(n)
WARMUP = 210           # bars needed before the first score (200d MA + slack)
HORIZONS = [1, 5, 20]  # forward-return horizons in trading days

# ── symbols the pillars consume ────────────────────────────────────────────
SECTORS = scoring.SECTOR_SYMBOLS
INDUSTRY = scoring.INDUSTRY_SYMBOLS
# everything that feeds a quote or a history
ALL_SYMBOLS = sorted(set(
    ["SPY", "QQQ", "RSP", "IWM",
     "^VIX", "^VIX3M", "^VIX9D", "^SKEW",
     "TQQQ", "SQQQ", "UVXY",
     "^TNX", "^IRX", "DX-Y.NYB", "TLT", "HYG", "LQD", "GLD",
     "BTC-USD"]
    + SECTORS + INDUSTRY
))


# ── data download ───────────────────────────────────────────────────────────
def _yf_url(sym: str) -> str:
    import urllib.parse
    s = urllib.parse.quote(sym, safe="")
    p1 = int(datetime.strptime(DOWNLOAD_START, "%Y-%m-%d")
             .replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time())
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{s}"
            f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")


def _fetch(sym: str) -> dict | None:
    """Return {dates:[iso], adjclose:[float|None], open/high/low/volume:[...]}."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(_yf_url(sym),
                                         headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=20).read()
            d = json.loads(raw)
            res = d["chart"]["result"][0]
            ts = res["timestamp"]
            ind = res["indicators"]
            q = ind["quote"][0]
            adj = ind.get("adjclose", [{}])[0].get("adjclose")
            closes = q.get("close", [])
            # Prefer adjusted close; fall back to raw close where adj is missing.
            if adj is None:
                adj = closes
            dates = [datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
                     for t in ts]
            return {
                "dates": dates,
                "adjclose": adj,
                "close": closes,
                "open": q.get("open", []),
                "high": q.get("high", []),
                "low": q.get("low", []),
                "volume": q.get("volume", []),
            }
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                TimeoutError, json.JSONDecodeError) as e:
            if attempt == 2:
                print(f"  ! {sym}: fetch failed ({type(e).__name__})", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def load_all(refresh: bool = False) -> dict[str, dict]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    out: dict[str, dict] = {}
    for sym in ALL_SYMBOLS:
        cache = os.path.join(CACHE_DIR, sym.replace("/", "_").replace("^", "_") + ".json")
        if not refresh and os.path.exists(cache):
            with open(cache) as f:
                data = json.load(f)
            if "open" in data:
                out[sym] = data
                continue
            print(f"  {sym}: cached payload lacks 'open' — refetching …")
        else:
            print(f"  downloading {sym} …")
        data = _fetch(sym)
        if data:
            with open(cache, "w") as f:
                json.dump(data, f)
            out[sym] = data
        time.sleep(0.3)  # be polite to Yahoo
    return out


# ── align everything onto SPY's trading-day axis ─────────────────────────────
def align(raw: dict[str, dict]) -> tuple[list[str], dict[str, list]]:
    """Return (master_dates, {sym: [adjclose aligned to master, ffilled]})."""
    master = raw["SPY"]["dates"]
    idx = {dt: i for i, dt in enumerate(master)}
    aligned: dict[str, list] = {}
    for sym, d in raw.items():
        series = [None] * len(master)
        for dt, px in zip(d["dates"], d["adjclose"]):
            if dt in idx and px is not None and px > 0:
                series[idx[dt]] = float(px)
        # forward-fill small gaps (ETFs share SPY's calendar; gaps are rare)
        last = None
        for i in range(len(series)):
            if series[i] is None:
                series[i] = last
            else:
                last = series[i]
        aligned[sym] = series
    # SPY OHLCV (raw OHLC; SPY hasn't split in the modern window)
    spy = raw["SPY"]
    spy_ax = {dt: i for i, dt in enumerate(spy["dates"])}
    def col(name):
        s = [None] * len(master)
        for dt, v in zip(spy["dates"], spy.get(name, [])):
            if dt in idx:
                s[idx[dt]] = v
        return s
    aligned["__SPY_HIGH"] = col("high")
    aligned["__SPY_LOW"] = col("low")
    aligned["__SPY_VOL"] = col("volume")
    aligned["__SPY_OPEN"] = col("open")
    aligned["__SPY_CLOSE_RAW"] = col("close")
    return master, aligned


# ── reconstruct one day's quotes + histories, score it ───────────────────────
def _quote(series: list, i: int) -> dict | None:
    px = series[i]
    if px is None:
        return None
    prev = series[i - 1] if i > 0 else None
    chg = ((px / prev - 1) * 100) if (prev and prev > 0) else 0.0
    return {"price": px, "changePct": chg, "source": "yahoo"}


def _hist(series: list, i: int) -> list:
    lo = max(0, i - WINDOW + 1)
    return [c for c in series[lo: i + 1] if c is not None]


def score_day(i: int, aligned: dict[str, list]) -> dict | None:
    """Replay the live engine for master-index i. Returns dict or None."""
    quotes = {sym: _quote(aligned[sym], i) for sym in ALL_SYMBOLS}
    # BTC quote key in the engine is a plain dict via btc_q
    btc_q = quotes.get("BTC-USD")

    spy_closes = _hist(aligned["SPY"], i)
    qqq_closes = _hist(aligned["QQQ"], i)
    rsp_closes = _hist(aligned["RSP"], i)
    vix_closes = _hist(aligned["^VIX"], i)
    tnx_closes = _hist(aligned["^TNX"], i)
    dxy_closes = _hist(aligned["DX-Y.NYB"], i)
    hyg_closes = _hist(aligned["HYG"], i)
    lqd_closes = _hist(aligned["LQD"], i)
    btc_closes = _hist(aligned["BTC-USD"], i)
    sector_hist = {s: _hist(aligned[s], i) for s in SECTORS}

    lo = max(0, i - WINDOW + 1)
    spy_ohlcv = {
        "highs":   [v for v in aligned["__SPY_HIGH"][lo: i + 1] if v is not None],
        "lows":    [v for v in aligned["__SPY_LOW"][lo: i + 1] if v is not None],
        "closes":  spy_closes,
        "volumes": [v for v in aligned["__SPY_VOL"][lo: i + 1] if v is not None],
    }

    def safe(fn, *a):
        try:
            return fn(*a)
        except Exception:
            return {"score": 50, "details": {}, "reasons": []}

    vol = safe(scoring.score_volatility, quotes, vix_closes)
    tr  = safe(scoring.score_trend, quotes, spy_closes, qqq_closes, spy_ohlcv)
    br  = safe(scoring.score_breadth, quotes, rsp_closes, sector_hist)
    mo  = safe(scoring.score_momentum, quotes, sector_hist)
    # macro: neutralize calendar overlays (fomc/opex/season)
    mac = safe(scoring.score_macro, quotes, tnx_closes, dxy_closes,
               btc_q, btc_closes, {"days_until": None},
               hyg_closes, lqd_closes, None, None)

    raw_total = int(
        vol["score"] * PILLAR_WEIGHTS["volatility"] +
        tr["score"]  * PILLAR_WEIGHTS["trend"] +
        br["score"]  * PILLAR_WEIGHTS["breadth"] +
        mo["score"]  * PILLAR_WEIGHTS["momentum"] +
        mac["score"] * PILLAR_WEIGHTS["macro"]
    )

    # faithful safety overrides (data_quality always valid here)
    total = raw_total
    vix_level = vol["details"].get("vix_level") or 0
    above_200 = tr["details"].get("above_200", True)
    if vix_level >= scoring.VIX_FLOOR_CRISIS:
        total = min(total, 39)
    elif vix_level >= scoring.VIX_FLOOR_HIGH:
        total = min(total, 47)
    elif vix_level >= scoring.VIX_FLOOR_MODERATE:
        total = min(total, 57)
    if not above_200:
        total = min(total, 54)

    decision, _, _ = scoring.decision_for_score(total)
    # mean-reversion features (Connors RSI-2 + distance from 20d MA)
    rsi2 = scoring.wilder_rsi(spy_closes, 2)
    ma20 = scoring.simple_ma(spy_closes, 20)
    dist20 = ((spy_closes[-1] / ma20 - 1) * 100) if (ma20 and spy_closes) else None
    return {
        "total": total, "raw_total": raw_total, "decision": decision,
        "above_200": bool(above_200),
        "v": vol["score"], "tr": tr["score"], "br": br["score"],
        "mo": mo["score"], "ma": mac["score"],
        "rsi2": rsi2 if rsi2 is not None else "",
        "dist20": round(dist20, 3) if dist20 is not None else "",
    }


# ── statistics (stdlib only) ─────────────────────────────────────────────────
def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va == 0 or vb == 0:
        return float("nan")
    return cov / math.sqrt(va * vb)


def spearman(a: list[float], b: list[float]) -> float:
    return _pearson(_rank(a), _rank(b))


def _mean(xs): return sum(xs) / len(xs) if xs else float("nan")
def _std(xs):
    if len(xs) < 2: return float("nan")
    m = _mean(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def max_drawdown(equity: list[float]) -> float:
    peak, mdd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return mdd


# ── main ──────────────────────────────────────────────────────────────────
# Derive bands from the LIVE engine so a decision-label rename can never
# silently break the replay (the old hardcoded "YES"/"CAUTION" list did
# exactly that when bands were renamed to RISK-ON/…/RISK-OFF).
BANDS = [b["decision"] for b in scoring.DECISION_BANDS]
ENGAGE_MIN = 55      # "engage" line per README — SELECTIVE and above
FULL_RISK_MIN = 70   # CONSTRUCTIVE and above


def run(refresh: bool = False):
    print("Loading data (cached after first run)…")
    raw = load_all(refresh=refresh)
    missing = [s for s in ALL_SYMBOLS if s not in raw]
    if "SPY" not in raw:
        print("FATAL: no SPY data; cannot run.", file=sys.stderr)
        sys.exit(1)
    if missing:
        print(f"  (note: {len(missing)} symbols unavailable, pillars degrade gracefully: {missing})")

    master, aligned = align(raw)
    # ensure every symbol key exists (None series) so score_day doesn't KeyError
    for s in ALL_SYMBOLS:
        aligned.setdefault(s, [None] * len(master))

    spy = aligned["SPY"]
    spy_open = aligned["__SPY_OPEN"]
    spy_high = aligned["__SPY_HIGH"]
    spy_low = aligned["__SPY_LOW"]
    spy_close_raw = aligned["__SPY_CLOSE_RAW"]
    n = len(master)
    print(f"Replaying {n - WARMUP - max(HORIZONS)} trading days "
          f"({master[WARMUP]} → {master[n - max(HORIZONS) - 1]})…\n")

    rows = []
    last = n - max(HORIZONS)
    for i in range(WARMUP, last):
        if spy[i] is None or spy[i - 1] is None:
            continue
        if master[i] < ANALYSIS_START:
            continue
        s = score_day(i, aligned)
        if s is None:
            continue
        fwd = {}
        ok = True
        for h in HORIZONS:
            base, fut = spy[i], spy[i + h]
            if base and fut:
                fwd[h] = (fut / base - 1) * 100
            else:
                ok = False
        if not ok:
            continue
        nd = {
            "nd_open": spy_open[i + 1], "nd_high": spy_high[i + 1],
            "nd_low": spy_low[i + 1], "nd_close": spy_close_raw[i + 1],
            "nd_prev_close": spy_close_raw[i],
        }
        rows.append({"date": master[i], **s,
                     **{f"fwd{h}": fwd[h] for h in HORIZONS},
                     **{k: (v if v is not None else "") for k, v in nd.items()}})

    if len(rows) < 100:
        print(f"Only {len(rows)} scored days — insufficient for inference.")
        return

    _report(rows)
    # dump raw for inspection
    with open("backtest_results.csv", "w") as f:
        cols = (["date", "total", "raw_total", "decision", "above_200",
                 "v", "tr", "br", "mo", "ma", "rsi2", "dist20"]
                + [f"fwd{h}" for h in HORIZONS]
                + ["nd_open", "nd_high", "nd_low", "nd_close", "nd_prev_close"])
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print("\nPer-day detail written to backtest_results.csv")


def _report(rows: list[dict]):
    n = len(rows)
    print("=" * 72)
    print(f"  MARKET QUALITY SCORE — PREDICTIVE-POWER BACKTEST  ({n} days)")
    print("=" * 72)

    # 1) Information Coefficient: Spearman(score, forward return)
    print("\n[1] INFORMATION COEFFICIENT  — Spearman corr(score, fwd return)")
    print("    (the headline: >0 means higher score → higher forward return)")
    for h in HORIZONS:
        ic = spearman([r["total"] for r in rows], [r[f"fwd{h}"] for r in rows])
        print(f"    {h:>2}-day fwd:  IC = {ic:+.3f}")

    # 2) Forward return by decision band
    print("\n[2] FORWARD 5-DAY RETURN BY DECISION BAND")
    print(f"    {'band':<12} {'n':>5} {'mean%':>8} {'median%':>8} {'hit%':>6} {'std%':>7}")
    base_mean = _mean([r["fwd5"] for r in rows])
    for band in BANDS:
        sub = [r["fwd5"] for r in rows if r["decision"] == band]
        if not sub:
            print(f"    {band:<12} {0:>5}   (no days)")
            continue
        hit = 100 * sum(1 for x in sub if x > 0) / len(sub)
        print(f"    {band:<12} {len(sub):>5} {_mean(sub):>+8.3f} "
              f"{sorted(sub)[len(sub)//2]:>+8.3f} {hit:>5.1f}% {_std(sub):>7.3f}")
    print(f"    {'ALL (b/h)':<12} {n:>5} {base_mean:>+8.3f}   "
          f"(unconditional baseline — beat THIS to add value)")

    # 3) Score decile monotonicity
    print("\n[3] FORWARD 5-DAY RETURN BY SCORE DECILE  (monotone rise = real signal)")
    srt = sorted(rows, key=lambda r: r["total"])
    for d in range(10):
        lo, hi = d * n // 10, (d + 1) * n // 10
        chunk = srt[lo:hi]
        if not chunk:
            continue
        sc = [r["total"] for r in chunk]
        fr = [r["fwd5"] for r in chunk]
        hit = 100 * sum(1 for x in fr if x > 0) / len(fr)
        print(f"    D{d+1:<2} score[{min(sc):>3}-{max(sc):>3}]  "
              f"n={len(chunk):>4}  mean fwd5 = {_mean(fr):>+7.3f}%  hit={hit:>5.1f}%")

    # 3b) Per-pillar IC — which components carry signal vs drag?
    print("\n[3b] PER-PILLAR INFORMATION COEFFICIENT  (Spearman vs fwd return)")
    print("     positive = that pillar predicts gains; negative = it's a drag")
    pillar_keys = [("v", "Volatility"), ("tr", "Trend"), ("br", "Breadth"),
                   ("mo", "Momentum"), ("ma", "Macro"), ("total", "TOTAL")]
    print(f"     {'pillar':<12} {'IC-5d':>8} {'IC-20d':>8}")
    for key, name in pillar_keys:
        ic5 = spearman([r[key] for r in rows], [r["fwd5"] for r in rows])
        ic20 = spearman([r[key] for r in rows], [r["fwd20"] for r in rows])
        print(f"     {name:<12} {ic5:>+8.3f} {ic20:>+8.3f}")

    # 3c) Per-calendar-year — does the score help in bad years?
    print("\n[3c] BY CALENDAR YEAR  — B&H vs filter; does it dodge bad years?")
    print(f"     {'yr':<5} {'n':>4} {'B&H mean5':>10} {'≥55 mean5':>10} {'expo%':>6} {'IC-5d':>7}")
    years = sorted({r["date"][:4] for r in rows})
    for y in years:
        sub = [r for r in rows if r["date"][:4] == y]
        if len(sub) < 20:
            continue
        bh = _mean([r["fwd5"] for r in sub])
        inv = [r["fwd5"] for r in sub if r["total"] >= ENGAGE_MIN]
        filt = (sum(inv) / len(sub)) if sub else 0.0  # avg incl. flat (out) days
        expo = 100 * len(inv) / len(sub)
        ic = spearman([r["total"] for r in sub], [r["fwd5"] for r in sub])
        flag = "  <-- bad yr" if bh < 0 else ""
        print(f"     {y:<5} {len(sub):>4} {bh:>+10.3f} {filt:>+10.3f} {expo:>5.0f}% {ic:>+7.3f}{flag}")

    # 3d) Regime split — bull tape (SPY>200d) vs bear tape (SPY<200d)
    print("\n[3d] REGIME SPLIT  — IC and returns in bull vs bear tape (SPY vs its 200d)")
    for label, sub in [("Bull (SPY>200d)", [r for r in rows if r["above_200"]]),
                       ("Bear (SPY<200d)", [r for r in rows if not r["above_200"]])]:
        if len(sub) < 30:
            print(f"     {label:<18} (only {len(sub)} days)")
            continue
        ic = spearman([r["total"] for r in sub], [r["fwd5"] for r in sub])
        bh = _mean([r["fwd5"] for r in sub])
        print(f"     {label:<18} n={len(sub):>5}  IC-5d={ic:>+.3f}  B&H mean5={bh:>+.3f}%")

    # 3e) Pillar cross-correlation — how many independent signals do we really have?
    print("\n[3e] PILLAR SCORE CROSS-CORRELATION  (Pearson, daily scores)")
    print("     High values mean pillars co-move (shared beta regime) —")
    print("     the composite has fewer independent degrees of freedom than 5.")
    pk = [("v", "Vol"), ("tr", "Trend"), ("br", "Brdth"), ("mo", "Mom"), ("ma", "Macro")]
    print("     " + " " * 7 + "".join(f"{nm:>7}" for _, nm in pk))
    for key_i, name_i in pk:
        cells = []
        for key_j, _ in pk:
            c = pearson([r[key_i] for r in rows], [r[key_j] for r in rows])
            cells.append(f"{c:>+7.2f}")
        print(f"     {name_i:<7}" + "".join(cells))

    # 4) Strategy vs buy & hold (5-day non-overlapping rebalances)
    print(f"\n[4] STRATEGY TEST — long SPY only when score clears a band floor")
    print("    vs buy-&-hold. Non-overlapping 5-day holding periods.")
    for label, cond in [(f"Score≥{FULL_RISK_MIN} (CONSTRUCTIVE+)", lambda r: r["total"] >= FULL_RISK_MIN),
                        (f"Score≥{ENGAGE_MIN} (SELECTIVE+)",    lambda r: r["total"] >= ENGAGE_MIN)]:
        _strategy(rows, cond, label)
    _strategy(rows, lambda r: True, "Buy & Hold")


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation, stdlib only."""
    n = min(len(xs), len(ys))
    if n < 2:
        return float("nan")
    xs, ys = xs[:n], ys[:n]
    mx, my = _mean(xs), _mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx  = sum((x - mx) ** 2 for x in xs)
    vy  = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(vx * vy)
    return cov / denom if denom else float("nan")


def _strategy(rows, cond, label):
    # step through in 5-day blocks; if cond true at block start, hold SPY 5d
    eq_strat, eq_days = 1.0, 0
    curve = [1.0]
    i = 0
    invested_blocks = 0
    total_blocks = 0
    while i < len(rows):
        r = rows[i]
        total_blocks += 1
        if cond(r):
            eq_strat *= (1 + r["fwd5"] / 100)
            eq_days += 5
            invested_blocks += 1
        curve.append(eq_strat)
        i += 5
    years = (len(rows) / 252.0)
    cagr = (eq_strat ** (1 / years) - 1) * 100 if years > 0 and eq_strat > 0 else float("nan")
    # per-block returns for Sharpe
    blocks = []
    i = 0
    while i < len(rows):
        r = rows[i]
        blocks.append(r["fwd5"] / 100 if cond(r) else 0.0)
        i += 5
    mu, sd = _mean(blocks), _std(blocks)
    sharpe = (mu / sd * math.sqrt(252 / 5)) if sd and sd > 0 else float("nan")
    expo = 100 * invested_blocks / total_blocks if total_blocks else 0
    print(f"    {label:<22} totalRet={ (eq_strat-1)*100:>+7.1f}%  "
          f"CAGR={cagr:>+6.2f}%  Sharpe={sharpe:>5.2f}  "
          f"maxDD={max_drawdown(curve)*100:>6.1f}%  exposure={expo:>4.0f}%")


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
