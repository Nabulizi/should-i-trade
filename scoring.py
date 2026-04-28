"""
scoring.py — 5-pillar market quality engine.

Each pillar scores 0–100. Total = weighted sum.
Each pillar returns {score, details, reasons} where `reasons` is an
ordered list of "+N / -N label" strings explaining exactly how the
score was built. This removes the "black box" problem.
"""

from __future__ import annotations
import sys, time
from typing import Any

from data import (
    fetch_quotes_parallel, fetch_histories_parallel,
    btc_quote, btc_history, market_state, fomc_proximity, econ_proximity,
)

# ─── configuration ─────────────────────────────────────────────────────────
PILLAR_WEIGHTS = {
    "volatility": 0.20,
    "trend":      0.25,
    "breadth":    0.20,
    "momentum":   0.20,
    "macro":      0.15,
}

SECTOR_SYMBOLS = ["XLY", "XLC", "XLF", "XLK", "XLE", "XLI",
                  "XLV", "XLU", "XLP", "XLRE", "XLB"]
SECTOR_NAMES = {
    "XLY": "Cons Disc", "XLC": "Comm Svcs", "XLF": "Financials",
    "XLK": "Technology", "XLE": "Energy",   "XLI": "Industrials",
    "XLV": "Health Care","XLU": "Utilities","XLP": "Cons Staples",
    "XLRE": "Real Estate","XLB": "Materials",
}

# Industry subsector ETFs — high-signal for breadth under the surface.
INDUSTRY_SYMBOLS = ["SMH", "XBI", "KRE", "ITB", "IYT", "XRT", "KWEB", "ARKK", "IWM"]
INDUSTRY_NAMES = {
    "SMH": "Semis",        "XBI": "Biotech",    "KRE": "Reg Banks",
    "ITB": "Homebuilders", "IYT": "Transports", "XRT": "Retail",
    "KWEB": "China Tech",  "ARKK": "Spec Growth","IWM": "Small Caps",
}

# Everything the dashboard needs in one shot.
CORE_SYMBOLS = ["SPY", "QQQ", "RSP", "^VIX", "^VIX3M", "TLT", "^TNX",
                "DX-Y.NYB", "TQQQ", "SQQQ", "UVXY", "HYG", "GLD"]


# ─── math primitives ───────────────────────────────────────────────────────
def simple_ma(closes: list[float], n: int) -> float | None:
    sl = [c for c in closes[-n:] if c is not None]
    if len(sl) < max(1, int(n * 0.75)):
        return None
    return sum(sl) / len(sl)


def wilder_rsi(closes: list[float], n: int = 14) -> float | None:
    """Proper Wilder-smoothed RSI(n). Returns 0-100 or None if insufficient data."""
    if len(closes) < n + 1:
        return None
    gains, losses = 0.0, 0.0
    # First n-period simple average
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0: gains += d
        else:      losses -= d
    avg_g = gains / n
    avg_l = losses / n
    # Wilder smoothing for the rest
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = d if d > 0 else 0
        l = -d if d < 0 else 0
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 1)


def percentile_1y(closes: list[float]) -> int:
    yr = [c for c in closes[-252:] if c is not None]
    if not yr: return 50
    cur = closes[-1]
    return round(len([c for c in yr if c < cur]) / len(yr) * 100)


def compute_mas(closes: list[float]) -> dict:
    return {
        "ma20":    round(simple_ma(closes, 20), 4)  if simple_ma(closes, 20)  else None,
        "ma50":    round(simple_ma(closes, 50), 4)  if simple_ma(closes, 50)  else None,
        "ma200":   round(simple_ma(closes, 200), 4) if simple_ma(closes, 200) else None,
        "rsi14":   wilder_rsi(closes, 14),
        "pctile":  percentile_1y(closes),
    }


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(v)))


def pct(q, key="changePct"):
    return (q.get(key) or 0) if q else 0


def price(q):
    return q.get("price") if q else None


# ─── pillar 1 — volatility ─────────────────────────────────────────────────
def score_volatility(quotes: dict, vix_closes: list[float]) -> dict:
    vix_q = quotes.get("^VIX")
    tqqq_q, sqqq_q, uvxy_q = quotes.get("TQQQ"), quotes.get("SQQQ"), quotes.get("UVXY")
    vix_val = price(vix_q)

    score = 50
    reasons: list[str] = []
    details: dict[str, Any] = {"vix_level": None, "vix_label": "N/A", "vix_color": "gray"}

    if vix_val is None:
        details["vix_level"] = None
        reasons.append("⚪ VIX unavailable — neutral 50")
        return {"score": 50, "details": details, "reasons": reasons}

    # VIX level
    if   vix_val < 15: d, lbl, col = +25, "Low",      "yellow"
    elif vix_val < 19: d, lbl, col = +35, "Moderate", "green"
    elif vix_val < 25: d, lbl, col = +10, "Elevated", "orange"
    elif vix_val < 30: d, lbl, col = -10, "High",     "red"
    else:              d, lbl, col = -30, "Extreme",  "red"
    score += d
    reasons.append(f"{'+' if d>=0 else ''}{d} VIX {vix_val:.2f} → {lbl}")
    details.update(vix_level=round(vix_val, 2), vix_label=lbl, vix_color=col)

    # VIX trend
    vix_chg = pct(vix_q)
    if   vix_chg < -3: d, lbl, col = +12, "Falling", "green"
    elif vix_chg <  0: d, lbl, col = +5,  "Calming", "green"
    elif vix_chg <  3: d, lbl, col = -5,  "Rising",  "orange"
    else:              d, lbl, col = -15, "Spiking", "red"
    score += d
    reasons.append(f"{'+' if d>=0 else ''}{d} VIX {lbl} ({vix_chg:+.2f}%)")
    details.update(vix_trend=lbl, vix_trend_color=col, vix_change_pct=round(vix_chg, 2))

    # VIX 1Y percentile — require ≥20 data points; single-value fallback gives misleading 0th %ile
    vix_1y = [c for c in (vix_closes or []) if c is not None]
    if len(vix_1y) >= 20:
        vix_pct = round(len([c for c in vix_1y if c < vix_val]) / len(vix_1y) * 100)
        if   vix_pct < 25: score += 5;  reasons.append(f"+5 VIX at {vix_pct}th %ile (calm zone)")
        elif vix_pct > 75: score -= 10; reasons.append(f"-10 VIX at {vix_pct}th %ile (fear zone)")
        details["vix_pctile"] = vix_pct
    else:
        details["vix_pctile"] = None

    # Flow Sentiment proxy — TQQQ/SQQQ net + UVXY fear. NOT a put/call ratio;
    # we display an honest "Flow Sentiment" 0-100 score instead of fake P/C number.
    bull = pct(tqqq_q)
    bear = pct(sqqq_q)
    uvxy = pct(uvxy_q)
    net = bull - bear

    if   net > 7:  flow, flbl, fcol = 85, "Strong Risk-On",  "green"
    elif net > 4:  flow, flbl, fcol = 70, "Risk-On",         "green"
    elif net > 1:  flow, flbl, fcol = 55, "Tilting Bullish", "yellow"
    elif net > -2: flow, flbl, fcol = 45, "Neutral",         "yellow"
    elif net > -5: flow, flbl, fcol = 30, "Tilting Bearish", "orange"
    else:          flow, flbl, fcol = 15, "Risk-Off",        "red"

    if uvxy > 5:  flow -= 10
    if uvxy < -5: flow += 8
    flow = clamp(flow)

    if   flow >= 70: d = +8
    elif flow >= 50: d = +4
    elif flow >= 35: d = -3
    else:            d = -12
    score += d
    reasons.append(f"{'+' if d>=0 else ''}{d} Flow {flow}/100 → {flbl}")
    details.update(
        flow_score=flow, flow_label=flbl, flow_color=fcol,
        tqqq_chg=round(bull, 2), sqqq_chg=round(bear, 2), uvxy_chg=round(uvxy, 2),
    )

    # VIX Term Structure — VIX vs VIX3M (3-month forward vol expectation)
    # Backwardation (VIX > VIX3M) = near-term fear spike = negative
    # Steep contango (VIX3M >> VIX) = calm, fear priced further out = positive
    vix3m_q = quotes.get("^VIX3M")
    vix3m_val = price(vix3m_q)
    vix_term_label, vix_term_color = "N/A", "gray"
    vix_vs_vix3m = None
    if vix_val and vix3m_val and vix3m_val > 0:
        ratio = round(vix_val / vix3m_val, 3)
        vix_vs_vix3m = ratio
        if ratio > 1.05:
            d, vix_term_label, vix_term_color = -10, "Backwardation", "red"
            score += d
            reasons.append(f"{d} VIX/VIX3M {ratio:.2f}x — fear spike, backwardation")
        elif ratio < 0.90:
            d, vix_term_label, vix_term_color = +8, "Steep Contango", "green"
            score += d
            reasons.append(f"+{d} VIX/VIX3M {ratio:.2f}x — calm, fear priced further out")
        else:
            vix_term_label, vix_term_color = "Contango", "yellow"
            reasons.append(f"+0 VIX/VIX3M {ratio:.2f}x — normal contango")
    details.update(
        vix3m_value=round(vix3m_val, 2) if vix3m_val else None,
        vix_term_label=vix_term_label, vix_term_color=vix_term_color,
        vix_vs_vix3m=vix_vs_vix3m,
    )

    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 2 — trend ──────────────────────────────────────────────────────
def score_trend(quotes: dict, spy_closes: list[float], qqq_closes: list[float]) -> dict:
    spy_q, qqq_q = quotes.get("SPY"), quotes.get("QQQ")
    spy_px, qqq_px = price(spy_q), price(qqq_q)
    spy_mas = compute_mas(spy_closes) if spy_closes else {}
    qqq_mas = compute_mas(qqq_closes) if qqq_closes else {}

    ma20, ma50, ma200 = spy_mas.get("ma20"), spy_mas.get("ma50"), spy_mas.get("ma200")
    q50, q200 = qqq_mas.get("ma50"), qqq_mas.get("ma200")
    above_20  = bool(spy_px and ma20  and spy_px > ma20)
    above_50  = bool(spy_px and ma50  and spy_px > ma50)
    above_200 = bool(spy_px and ma200 and spy_px > ma200)
    qqq_a50   = bool(qqq_px and q50   and qqq_px > q50)
    qqq_a200  = bool(qqq_px and q200  and qqq_px > q200)

    score = 0
    reasons: list[str] = []
    for ok, pts, label in [(above_20, 25, "SPY > 20d"),
                            (above_50, 30, "SPY > 50d"),
                            (above_200, 30, "SPY > 200d"),
                            (qqq_a50, 15, "QQQ > 50d")]:
        if ok:
            score += pts
            reasons.append(f"+{pts} {label}")
        else:
            reasons.append(f"+0 {label.replace('>', '<')}")

    # Regime label
    if   above_20 and above_50 and above_200: regime, rc = "Uptrend", "green"
    elif above_50 and above_200:              regime, rc = "Recovering", "yellow"
    elif above_200:                           regime, rc = "Mixed", "orange"
    else:                                     regime, rc = "Downtrend", "red"

    rsi = spy_mas.get("rsi14")
    if rsi is not None:
        if   rsi >= 75: reasons.append(f"⚠ RSI {rsi} — severely overbought")
        elif rsi >= 70: reasons.append(f"ℹ RSI {rsi} — overbought")
        elif rsi <= 30: reasons.append(f"ℹ RSI {rsi} — oversold, bounce candidate")

    spy_1y_hi = max(spy_closes[-252:]) if len(spy_closes) >= 252 else (max(spy_closes) if spy_closes else spy_px or 1)
    ath_dist = round((spy_px / spy_1y_hi - 1) * 100, 1) if spy_px and spy_1y_hi else 0

    details = {
        "spy_price": round(spy_px, 2) if spy_px else None,
        "spy_change_pct": round(pct(spy_q), 2),
        "qqq_price": round(qqq_px, 2) if qqq_px else None,
        "qqq_change_pct": round(pct(qqq_q), 2),
        "ma20":  round(ma20, 2)  if ma20  else None,
        "ma50":  round(ma50, 2)  if ma50  else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "above_20": above_20, "above_50": above_50, "above_200": above_200,
        "qqq_above_50": qqq_a50, "qqq_above_200": qqq_a200,
        "regime": regime, "regime_color": rc,
        "ath_dist": ath_dist,
        "rsi14": rsi,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 3 — breadth ────────────────────────────────────────────────────
def score_breadth(quotes: dict, rsp_closes: list[float]) -> dict:
    rsp_q, spy_q = quotes.get("RSP"), quotes.get("SPY")
    rsp_px = price(rsp_q)
    rsp_mas = compute_mas(rsp_closes) if rsp_closes else {}
    rsp_chg = pct(rsp_q)
    spy_chg = pct(spy_q)

    # Sector count — require changePct to be present so malformed quotes (missing key)
    # aren't silently counted as "flat/not-positive", making breadth look weaker than reality.
    sector_quotes = {s: quotes.get(s) for s in SECTOR_SYMBOLS}
    n_valid = sum(1 for q in sector_quotes.values() if q and q.get("changePct") is not None)
    n_pos   = sum(1 for q in sector_quotes.values() if q and q.get("changePct") is not None and pct(q) > 0)

    # Industry count (broader breadth signal)
    ind_quotes = {s: quotes.get(s) for s in INDUSTRY_SYMBOLS}
    ni_valid = sum(1 for q in ind_quotes.values() if q and q.get("changePct") is not None)
    ni_pos   = sum(1 for q in ind_quotes.values() if q and q.get("changePct") is not None and pct(q) > 0)

    rsp_a50  = bool(rsp_px and rsp_mas.get("ma50")  and rsp_px > rsp_mas["ma50"])
    rsp_a200 = bool(rsp_px and rsp_mas.get("ma200") and rsp_px > rsp_mas["ma200"])

    score = 0
    reasons: list[str] = []

    if n_valid:
        p = int(n_pos / n_valid * 35)     # sectors contribute up to 35 pts
        score += p
        reasons.append(f"+{p} Sectors {n_pos}/{n_valid} positive")

    if ni_valid:
        p = int(ni_pos / ni_valid * 25)   # industries contribute up to 25 pts
        score += p
        reasons.append(f"+{p} Industries {ni_pos}/{ni_valid} positive")

    if rsp_chg > 0:
        score += 10
        reasons.append(f"+10 RSP (equal-wt) up {rsp_chg:+.2f}%")
    else:
        reasons.append(f"+0 RSP {rsp_chg:+.2f}%")

    if rsp_a50:
        score += 15
        reasons.append("+15 RSP > 50d MA")
    if rsp_a200:
        score += 15
        reasons.append("+15 RSP > 200d MA")

    # Sector + industry data
    sector_data = {s: {"name": SECTOR_NAMES[s],
                        "change_pct": round(pct(q), 2),
                        "price": round(price(q) or 0, 2)}
                   for s, q in sector_quotes.items() if q}
    industry_data = {s: {"name": INDUSTRY_NAMES[s],
                          "change_pct": round(pct(q), 2),
                          "price": round(price(q) or 0, 2)}
                     for s, q in ind_quotes.items() if q}

    details = {
        "sectors_positive": n_pos, "sectors_total": n_valid,
        "industries_positive": ni_pos, "industries_total": ni_valid,
        "rsp_price": round(rsp_px, 2) if rsp_px else None,
        "rsp_change_pct": round(rsp_chg, 2),
        "rsp_above_50": rsp_a50, "rsp_above_200": rsp_a200,
        "spy_price": round(price(spy_q), 2) if spy_q else None,
        "spy_change_pct": round(spy_chg, 2),
        "rsp_vs_spy": round(rsp_chg - spy_chg, 2),
        "sector_data": sector_data,
        "industry_data": industry_data,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 4 — momentum ───────────────────────────────────────────────────
def score_momentum(quotes: dict) -> dict:
    spy_q, rsp_q = quotes.get("SPY"), quotes.get("RSP")
    rsp_chg, spy_chg = pct(rsp_q), pct(spy_q)
    rsp_vs_spy = round(rsp_chg - spy_chg, 2)
    rsp_outperf = rsp_vs_spy > 0

    # Growth sectors (momentum driver)
    growth = ["XLY", "XLC", "XLK"]
    n_growth_pos = sum(1 for s in growth if quotes.get(s) and pct(quotes[s]) > 0)

    # Sector leaderboard (for leader/laggard)
    sector_changes = [(s, pct(quotes[s])) for s in SECTOR_SYMBOLS if quotes.get(s)]
    sector_changes.sort(key=lambda x: x[1], reverse=True)
    leader = sector_changes[0] if sector_changes else ("--", 0)
    laggard = sector_changes[-1] if sector_changes else ("--", 0)

    # Participation from sector count
    n_pos = sum(1 for s in SECTOR_SYMBOLS if quotes.get(s) and pct(quotes[s]) > 0)
    n_valid = sum(1 for s in SECTOR_SYMBOLS if quotes.get(s))

    score = 0
    reasons: list[str] = []

    # Growth leadership
    p = n_growth_pos * 10
    score += p
    reasons.append(f"+{p} Growth sectors {n_growth_pos}/3 positive")

    # Small caps (IWM) vs SPY — risk appetite
    iwm_q = quotes.get("IWM")
    iwm_chg = pct(iwm_q)
    iwm_vs_spy = round(iwm_chg - spy_chg, 2)
    if iwm_vs_spy > 0.3:
        score += 15
        reasons.append(f"+15 IWM leading SPY ({iwm_vs_spy:+.2f}%) — risk-on")
    elif iwm_vs_spy < -0.3:
        reasons.append(f"+0 IWM lagging SPY ({iwm_vs_spy:+.2f}%) — defensive")

    # Equal-weight vs cap-weight
    if rsp_outperf:
        score += 20
        reasons.append(f"+20 RSP outperforming SPY ({rsp_vs_spy:+.2f}%) — broad rally")
    elif rsp_chg > 0:
        score += 10
        reasons.append(f"+10 RSP positive but lagging")
    else:
        reasons.append(f"+0 RSP {rsp_chg:+.2f}% — narrow market")

    # Leader strength
    if sector_changes and leader[1] > 1.0:
        score += 15
        reasons.append(f"+15 {SECTOR_NAMES.get(leader[0], leader[0])} up {leader[1]:+.2f}% — strong leadership")

    # Participation label
    if n_pos >= 8 or (n_pos >= 6 and rsp_outperf):
        participation, pc = "Broad", "green"
    elif n_pos >= 5 or rsp_outperf:
        participation, pc = "Selective", "yellow"
    else:
        participation, pc = "Narrow", "red"

    details = {
        "sectors_positive": n_pos, "sectors_total": n_valid,
        "sectors_label": f"{n_pos}/{n_valid}",
        "sectors_color": "green" if n_pos >= 8 else ("yellow" if n_pos >= 5 else "red"),
        "growth_leaders": n_growth_pos,
        "rsp_vs_spy": rsp_vs_spy,
        "rsp_outperforming": rsp_outperf,
        "iwm_price": round(price(iwm_q), 2) if iwm_q else None,
        "iwm_change_pct": round(iwm_chg, 2),
        "iwm_vs_spy": iwm_vs_spy,
        "leader":  {"symbol": leader[0],  "name": SECTOR_NAMES.get(leader[0], "--"),  "change_pct": round(leader[1], 2)},
        "laggard": {"symbol": laggard[0], "name": SECTOR_NAMES.get(laggard[0], "--"), "change_pct": round(laggard[1], 2)},
        "participation": participation, "participation_color": pc,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 5 — macro ──────────────────────────────────────────────────────
def score_macro(quotes: dict, tnx_closes: list[float], dxy_closes: list[float],
                btc_q: dict | None, btc_closes: list[float], fomc: dict,
                hyg_closes: list[float] | None = None) -> dict:
    tnx_q, dxy_q, tlt_q = quotes.get("^TNX"), quotes.get("DX-Y.NYB"), quotes.get("TLT")
    tnx_val, dxy_px = price(tnx_q), price(dxy_q)
    tnx_chg, dxy_chg, tlt_chg = pct(tnx_q), pct(dxy_q), pct(tlt_q)

    score = 50
    reasons: list[str] = []

    # Yield level
    yield_label = "N/A"
    if tnx_val is not None:
        if   tnx_val < 3.5: d, yield_label = +25, "Bullish"
        elif tnx_val < 4.0: d, yield_label = +15, "Favorable"
        elif tnx_val < 4.5: d, yield_label = +5,  "Neutral"
        elif tnx_val < 5.0: d, yield_label = -10, "Elevated"
        else:               d, yield_label = -25, "Restrictive"
        score += d
        reasons.append(f"{'+' if d>=0 else ''}{d} 10Y {tnx_val:.2f}% → {yield_label}")

    # Yield direction (20d MA)
    tnx_valid = [c for c in (tnx_closes or []) if c is not None]
    tnx_ma20 = simple_ma(tnx_valid, 20) if len(tnx_valid) >= 20 else None
    yield_dir, yield_color = "Flat", "yellow"
    if tnx_val and tnx_ma20:
        if   tnx_val < tnx_ma20 * 0.995:
            d, yield_dir, yield_color = +15, "Falling", "green"
            score += d
            reasons.append(f"+{d} Yields falling (below 20d MA)")
        elif tnx_val > tnx_ma20 * 1.005:
            d, yield_dir, yield_color = -10, "Rising", "red"
            score += d
            reasons.append(f"{d} Yields rising (above 20d MA)")

    # DXY trend (20d MA)
    dxy_valid = [c for c in (dxy_closes or []) if c is not None]
    dxy_ma20 = simple_ma(dxy_valid, 20) if len(dxy_valid) >= 20 else None
    dxy_label, dxy_color = "Neutral", "yellow"
    if dxy_px and dxy_ma20:
        if   dxy_px < dxy_ma20 * 0.995:
            d, dxy_label, dxy_color = +15, "Weakening", "green"
            score += d
            reasons.append(f"+{d} DXY weakening — supports equities")
        elif dxy_px > dxy_ma20 * 1.005:
            d, dxy_label, dxy_color = -10, "Strengthening", "red"
            score += d
            reasons.append(f"{d} DXY strengthening — headwind")

    # TLT as risk-off signal
    if tlt_chg > 0.5:
        reasons.append(f"+5 TLT {tlt_chg:+.2f}% — bonds bid")
        score += 5

    # BTC — liquidity / speculative appetite
    btc_px = price(btc_q)
    btc_chg = pct(btc_q)
    btc_label, btc_color, btc_trend, btc_trend_color = "N/A", "gray", "N/A", "gray"
    btc_from_high = None

    if btc_px and btc_closes:
        btc_valid = [c for c in btc_closes if c is not None]
        btc_ma20  = simple_ma(btc_valid, 20)  if len(btc_valid) >= 20 else None
        btc_ma50  = simple_ma(btc_valid, 50)  if len(btc_valid) >= 38 else None
        btc_ma200 = simple_ma(btc_valid, 200) if len(btc_valid) >= 150 else None
        btc_52w_hi = max(btc_valid[-252:]) if len(btc_valid) >= 20 else btc_px
        btc_from_high = round((btc_px / btc_52w_hi - 1) * 100, 1)

        a20  = bool(btc_ma20  and btc_px > btc_ma20)
        a50  = bool(btc_ma50  and btc_px > btc_ma50)
        a200 = bool(btc_ma200 and btc_px > btc_ma200)
        mini_golden = bool(btc_ma20 and btc_ma50 and btc_ma20 > btc_ma50)

        if a20 and a50 and a200:
            btc_trend, btc_trend_color = "Full Bull", "green"
            d = 10
        elif a20 and a50 and not a200:
            btc_trend, btc_trend_color = ("Recovering", "yellow") if mini_golden else ("Mixed", "yellow")
            d = 4
        elif a20 and not a50:
            btc_trend, btc_trend_color = "Early Bounce", "orange"
            d = 0
        else:
            btc_trend, btc_trend_color = "Bear", "red"
            d = -8
        score += d
        reasons.append(f"{'+' if d>=0 else ''}{d} BTC {btc_trend} — liquidity proxy")

        if a20 and a50 and a200:     btc_label, btc_color = "Risk On",  "green"
        elif a20 and a50:            btc_label, btc_color = "Cautious", "yellow"
        elif a20:                    btc_label, btc_color = "Neutral",  "yellow"
        else:                        btc_label, btc_color = "Risk Off", "red"

    # HYG Credit Spreads — high-yield bond health as credit stress indicator
    hyg_q = quotes.get("HYG")
    hyg_px = price(hyg_q)
    hyg_chg = pct(hyg_q)
    hyg_label, hyg_color = "N/A", "gray"
    hyg_ma50 = None
    if hyg_closes and len(hyg_closes) >= 38:
        hyg_ma50 = simple_ma(hyg_closes, 50)
        if hyg_px and hyg_ma50:
            if hyg_px > hyg_ma50 * 1.002:
                hyg_label, hyg_color = "Healthy", "green"
                score += 8
                reasons.append("+8 HYG above 50d — credit conditions healthy")
            elif hyg_px < hyg_ma50 * 0.998:
                hyg_label, hyg_color = "Stressed", "red"
                score -= 10
                reasons.append("-10 HYG below 50d — credit stress, risk-off signal")
            else:
                hyg_label, hyg_color = "Neutral", "yellow"

    # GLD (Gold) — flight-to-safety signal
    gld_q = quotes.get("GLD")
    gld_px = price(gld_q)
    gld_chg = pct(gld_q)
    spy_chg_for_gld = pct(quotes.get("SPY"))
    gld_label, gld_color = "N/A", "gray"
    if gld_q:
        if gld_chg > 0.8 and spy_chg_for_gld < 0:
            gld_label, gld_color = "Flight-to-Safety", "orange"
            score -= 5
            reasons.append(f"-5 GLD +{gld_chg:.2f}% / SPY {spy_chg_for_gld:+.2f}% — risk-off flight to gold")
        elif gld_chg > 0.5:
            gld_label, gld_color = "Rising", "yellow"
            reasons.append(f"+0 GLD rising {gld_chg:+.2f}% — monitoring")
        elif gld_chg < -0.5:
            gld_label, gld_color = "Falling", "green"
            score += 3
            reasons.append(f"+3 GLD declining {gld_chg:+.2f}% — risk appetite intact")
        else:
            gld_label, gld_color = "Flat", "gray"

    # FOMC event risk — dampen score if meeting is imminent (markets pin)
    fomc_days = fomc.get("days_until")
    if fomc_days is not None:
        if fomc_days <= 1:
            score -= 15
            reasons.append(f"-15 FOMC in {fomc_days}d — event-risk freeze")
        elif fomc_days <= 3:
            score -= 8
            reasons.append(f"-8 FOMC in {fomc_days}d — reduce size")
        elif fomc_days <= 7:
            score -= 3
            reasons.append(f"-3 FOMC in {fomc_days}d — stay nimble")

    details = {
        "tnx_value": round(tnx_val, 3) if tnx_val else None,
        "tnx_ma20":  round(tnx_ma20, 3) if tnx_ma20 else None,
        "tnx_change_pct": round(tnx_chg, 2),
        "yield_label": yield_label, "yield_direction": yield_dir, "yield_color": yield_color,
        "dxy_value": round(dxy_px, 2) if dxy_px else None,
        "dxy_ma20":  round(dxy_ma20, 2) if dxy_ma20 else None,
        "dxy_change_pct": round(dxy_chg, 2),
        "dxy_label": dxy_label, "dxy_color": dxy_color,
        "tlt_value": round(price(tlt_q), 2) if tlt_q else None,
        "tlt_change_pct": round(tlt_chg, 2),
        "hyg_price": round(hyg_px, 2) if hyg_px else None,
        "hyg_change_pct": round(hyg_chg, 2),
        "hyg_ma50": round(hyg_ma50, 2) if hyg_ma50 else None,
        "hyg_label": hyg_label, "hyg_color": hyg_color,
        "gld_price": round(gld_px, 2) if gld_px else None,
        "gld_change_pct": round(gld_chg, 2) if gld_q else None,
        "gld_label": gld_label, "gld_color": gld_color,
        "btc_price": round(btc_px, 0) if btc_px else None,
        "btc_change_pct": round(btc_chg, 2) if btc_px else None,
        "btc_from_high": btc_from_high,
        "btc_label": btc_label, "btc_color": btc_color,
        "btc_trend": btc_trend, "btc_trend_color": btc_trend_color,
        "fomc_days": fomc_days,
        "fomc_date": fomc.get("date_pretty"),
        "fomc_label": fomc.get("label"),
        "fomc_color": fomc.get("color"),
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── orchestrator ──────────────────────────────────────────────────────────
def _safe_pillar(fn, *args, name: str = "?") -> dict:
    """Call a pillar scorer; return neutral fallback on exception."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"[WARN] Pillar '{name}' raised: {e}", file=sys.stderr, flush=True)
        return {
            "score": 50,
            "details": {},
            "reasons": [f"⚠ {name} data unavailable — neutral 50"],
        }


def compute_dashboard() -> dict:
    """Fetch everything in parallel and score all 5 pillars."""
    all_symbols = CORE_SYMBOLS + SECTOR_SYMBOLS + INDUSTRY_SYMBOLS

    # Parallel fetch: quotes + histories + BTC
    quotes = fetch_quotes_parallel(all_symbols, max_workers=8)
    history_pairs = [("SPY", 220), ("QQQ", 220), ("RSP", 220),
                     ("^VIX", 252), ("^TNX", 60), ("DX-Y.NYB", 60),
                     ("HYG", 60)]
    histories = fetch_histories_parallel(history_pairs, max_workers=4)

    # BTC fetched separately (different sources)
    btc_q = btc_quote()
    btc_closes = btc_history()

    mstate = market_state()
    fomc = fomc_proximity()
    econ_events = econ_proximity()

    # Score each pillar (with graceful fallback per pillar)
    vol  = _safe_pillar(score_volatility, quotes, histories.get("^VIX", []), name="Volatility")
    tr   = _safe_pillar(score_trend, quotes, histories.get("SPY", []), histories.get("QQQ", []), name="Trend")
    br   = _safe_pillar(score_breadth, quotes, histories.get("RSP", []), name="Breadth")
    mom  = _safe_pillar(score_momentum, quotes, name="Momentum")
    mac  = _safe_pillar(score_macro, quotes,
                        histories.get("^TNX", []), histories.get("DX-Y.NYB", []),
                        btc_q, btc_closes, fomc, histories.get("HYG", []), name="Macro")

    # Weighted total
    total = int(vol["score"]  * PILLAR_WEIGHTS["volatility"] +
                tr["score"]   * PILLAR_WEIGHTS["trend"] +
                br["score"]   * PILLAR_WEIGHTS["breadth"] +
                mom["score"]  * PILLAR_WEIGHTS["momentum"] +
                mac["score"]  * PILLAR_WEIGHTS["macro"])

    if   total >= 80: decision, dc, pos = "YES",     "green",  "FULL SIZE"
    elif total >= 60: decision, dc, pos = "CAUTION", "yellow", "HALF SIZE"
    else:             decision, dc, pos = "NO",      "red",    "PRESERVE CAPITAL"

    # Ticker
    ticker = []
    for sym, label in [("SPY", "SPY"), ("QQQ", "QQQ"), ("^VIX", "VIX"),
                        ("TLT", "TLT"), ("^TNX", "TNX"), ("DX-Y.NYB", "DXY"),
                        ("RSP", "RSP"), ("IWM", "IWM")]:
        q = quotes.get(sym)
        if q:
            ticker.append({"symbol": label, "price": round(q.get("price") or 0, 2),
                            "change_pct": round(pct(q), 2), "up": pct(q) >= 0})
    if btc_q:
        ticker.insert(2, {"symbol": "BTC", "price": round(btc_q["price"], 0),
                          "change_pct": pct(btc_q), "up": pct(btc_q) >= 0})
    for s in SECTOR_SYMBOLS + INDUSTRY_SYMBOLS:
        q = quotes.get(s)
        if q:
            ticker.append({"symbol": s, "price": round(q.get("price") or 0, 2),
                            "change_pct": round(pct(q), 2), "up": pct(q) >= 0})

    # Data coverage for UI honesty
    requested = len(all_symbols)
    fetched = sum(1 for q in quotes.values() if q)
    failed = [s for s, q in quotes.items() if not q]

    return {
        "total_score": total,
        "decision": decision, "decision_color": dc, "position_size": pos,
        "market_state": mstate,
        "fomc": fomc,
        "econ_events": econ_events,
        "pillars": {
            "volatility": {"score": vol["score"],  "weight": 20, "details": vol["details"],  "reasons": vol["reasons"]},
            "trend":      {"score": tr["score"],   "weight": 25, "details": tr["details"],   "reasons": tr["reasons"]},
            "breadth":    {"score": br["score"],   "weight": 20, "details": br["details"],   "reasons": br["reasons"]},
            "momentum":   {"score": mom["score"],  "weight": 20, "details": mom["details"],  "reasons": mom["reasons"]},
            "macro":      {"score": mac["score"],  "weight": 15, "details": mac["details"],  "reasons": mac["reasons"]},
        },
        "ticker": ticker,
        "timestamp": time.strftime("%H:%M:%S UTC", time.gmtime()),
        "data_coverage": {"requested": requested, "fetched": fetched, "failed": failed},
    }
