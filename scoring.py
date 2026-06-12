"""
scoring.py — 5-pillar market quality engine.

Each pillar scores 0–100. Total = weighted sum.
Each pillar returns {score, details, reasons} where `reasons` is an
ordered list of "+N / -N label" strings explaining exactly how the
score was built. This removes the "black box" problem.
"""

from __future__ import annotations
import logging, time
from datetime import date

logger = logging.getLogger(__name__)
from concurrent.futures import ThreadPoolExecutor as _TPE
from typing import Any

from data import (
    get_quote, get_history, get_ohlcv,
    btc_quote, btc_history, market_state, fomc_proximity, econ_proximity,
    fetch_fear_greed_stock, fetch_fear_greed_crypto,
    opex_proximity, seasonality, earnings_season, fetch_futures_tape,
    yf_last_bar_date,
)
from config import PILLAR_WEIGHTS, VOL_TARGET_K, VOL_TARGET_WINDOW
from models import PillarResult, DashboardResult, VolTargetInfo

# ─── configuration ─────────────────────────────────────────────────────────

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
CORE_SYMBOLS = ["SPY", "QQQ", "RSP", "^VIX", "^VIX3M", "^VIX9D", "^SKEW",
                "TLT", "^TNX", "^IRX", "DX-Y.NYB", "TQQQ", "SQQQ", "UVXY",
                "HYG", "LQD", "GLD"]


MIN_DATA_COVERAGE = 0.80
CRITICAL_SYMBOLS = ["SPY", "QQQ", "RSP", "^VIX", "^VIX3M", "^TNX", "DX-Y.NYB", "HYG", "IWM"]
CRITICAL_HISTORY_REQUIREMENTS = {
    "SPY": 150,       # 200d MA with local 75% minimum
    "QQQ": 150,
    "RSP": 150,
    "^VIX": 20,      # percentile/regime context
    "^TNX": 20,      # 20d yield direction
    "DX-Y.NYB": 20,  # 20d dollar direction
    "HYG": 38,       # 50d credit health with local 75% minimum
}
MIN_SECTOR_HISTORY_SYMBOLS = 8
MIN_SECTOR_HISTORY_POINTS = 64
# Market-conditions gauge: the 2005-2026 replay (docs/backtest-report.md) shows
# the composite describes the current regime but has no demonstrated timing
# edge over same-exposure baselines. Labels describe conditions and a suggested
# exposure posture; they are not validated trade signals. 55/70/85 are
# descriptive bands, not proven thresholds.
DECISION_BANDS = [
    {"min": 85, "decision": "RISK-ON",      "color": "green",  "position": "FULL EXPOSURE",
     "action": "Full exposure — calm, trending tape, press the bid on A/B setups"},
    {"min": 70, "decision": "CONSTRUCTIVE", "color": "green",  "position": "STANDARD EXPOSURE",
     "action": "Standard exposure — constructive tape, run your normal game"},
    {"min": 55, "decision": "SELECTIVE",    "color": "yellow", "position": "MODERATE EXPOSURE",
     "action": "Moderate exposure — mixed tape, engage selectively, A+ setups, tight stops"},
    {"min": 40, "decision": "DE-RISK",      "color": "orange", "position": "REDUCED EXPOSURE",
     "action": "Reduced exposure — choppy tape, very selective or sit out"},
    {"min": 0,  "decision": "RISK-OFF",     "color": "red",    "position": "DEFENSIVE / FLAT",
     "action": "Defensive — stressed tape, protect capital, no new longs"},
]


def action_for_score(total: int) -> str:
    """Plain-language 'what do I actually do' hint for a composite score."""
    for band in DECISION_BANDS:
        if total >= band["min"]:
            return band["action"]
    return DECISION_BANDS[-1]["action"]

# ─── scoring thresholds ────────────────────────────────────────────────────
# Volatility pillar
VIX_CALM        = 15    # VIX below this → low vol, bonus points
VIX_MODERATE    = 19    # VIX below this → moderate vol
VIX_ELEVATED    = 25    # VIX below this → elevated vol
VIX_HIGH        = 30    # VIX below this → high vol; above → extreme

# VIX override floor thresholds — graduated position-size caps (see _apply_overrides)
# Historically, VIX 40–80 contains generational entries (Mar 2020, Oct 2022, Oct 2008).
# We cap score (reduce size) but never issue a flat "never trade" below VIX 50.
VIX_FLOOR_MODERATE = 35   # reduce size, caution (score capped at 57)
VIX_FLOOR_HIGH     = 40   # defined-risk entries only (score capped at 47)
VIX_FLOOR_CRISIS   = 50   # extreme crisis; very small size, defined risk (score capped at 39)
VIX_TREND_BIG   = 3     # % change threshold for "falling fast" / "spiking" labels
VIX_PCTILE_LOW  = 25    # 1Y percentile below this → calm zone bonus
VIX_PCTILE_HIGH = 75    # 1Y percentile above this → fear zone penalty
FLOW_NET_STRONG_BULL = 7   # TQQQ-SQQQ net % above this → Strong Risk-On
FLOW_NET_BULL        = 4
FLOW_NET_MILD_BULL   = 1
FLOW_NET_MILD_BEAR   = -2
FLOW_NET_BEAR        = -5
UVXY_FEAR_THRESHOLD  = 5   # UVXY day % above/below this adjusts flow score
VIX_TERM_BACKW  = 1.05  # VIX/VIX3M ratio above this → backwardation
VIX_TERM_STEEP  = 0.90  # VIX/VIX3M ratio below this → steep contango
VIX9D_FEAR      = 1.00  # VIX9D/VIX above this → near-term fear spike
VIX9D_CALM      = 0.90  # VIX9D/VIX below this → calm, event risk low
SKEW_EXTREME    = 150   # SKEW above → extreme tail-risk hedging
SKEW_ELEVATED   = 140   # SKEW above → elevated tail-risk hedging
SKEW_NORMAL     = 120   # SKEW above → normal; below → complacent

# Trend pillar
RSI_SEVERELY_OVERBOUGHT = 75
RSI_OVERBOUGHT          = 70
RSI_OVERSOLD            = 30
RSI_SWEET_SPOT_LOW      = 45   # Ideal swing-entry RSI zone
RSI_SWEET_SPOT_HIGH     = 60
VOL_HIGH_RATIO          = 1.2  # Today's volume vs 20d avg → "high volume"
VOL_LOW_RATIO           = 0.7  # Below this → "low conviction"
CHAR_RSI_EXTENDED       = 72   # RSI above → market character = Extended
CHAR_ATR_TRENDING       = 1.5  # ATR% above + BBW% above → Trending
CHAR_ATR_CHOPPY         = 0.6  # ATR% below OR BBW% below → Choppy
CHAR_BBW_TRENDING       = 8.0
CHAR_BBW_CHOPPY         = 3.0

# Breadth pillar
BREADTH_ABOVE200_BULL   = 73   # % of sectors above 200d MA → broad bull
BREADTH_ABOVE200_WEAK   = 36   # % below this → structural weakness

# Watchlist scoring thresholds live in config.py (WL_*) and are consumed by
# watchlist.py — kept in one place so they can't silently drift.


def decision_for_score(total: int) -> tuple[str, str, str]:
    for band in DECISION_BANDS:
        if total >= band["min"]:
            return band["decision"], band["color"], band["position"]
    return "RISK-OFF", "red", "DEFENSIVE / FLAT"


def build_data_quality(quotes: dict, requested: int, fetched: int, failed: list[str],
                       histories: dict | None = None,
                       sector_symbols: list[str] | None = None) -> dict:
    coverage = fetched / requested if requested else 0.0
    critical_missing = [s for s in CRITICAL_SYMBOLS if not quotes.get(s)]
    histories = histories or {}
    critical_history_missing = [
        {"symbol": s, "required": n, "found": len(histories.get(s, []) or [])}
        for s, n in CRITICAL_HISTORY_REQUIREMENTS.items()
        if len(histories.get(s, []) or []) < n
    ]
    sector_symbols = sector_symbols or SECTOR_SYMBOLS
    sector_history_valid = sum(
        1 for s in sector_symbols
        if len(histories.get(s, []) or []) >= MIN_SECTOR_HISTORY_POINTS
    )
    sector_history_ok = sector_history_valid >= MIN_SECTOR_HISTORY_SYMBOLS
    valid = (coverage >= MIN_DATA_COVERAGE and not critical_missing and
             not critical_history_missing and sector_history_ok)

    if valid:
        message = f"Live data OK: {fetched}/{requested} quotes and core histories fetched."
    elif fetched == 0:
        message = "No live market data fetched. Decision disabled until the data feed recovers."
    elif critical_missing:
        message = "Critical quote inputs missing. Decision disabled until core symbols recover."
    elif critical_history_missing:
        missing = ", ".join(x["symbol"] for x in critical_history_missing[:4])
        tail = "..." if len(critical_history_missing) > 4 else ""
        message = f"Critical history inputs missing ({missing}{tail}). Decision disabled."
    elif not sector_history_ok:
        message = "Sector history coverage too low. Decision disabled until breadth context recovers."
    else:
        message = "Too many market symbols failed. Decision disabled until coverage improves."

    return {
        "valid": valid,
        "coverage_pct": round(coverage * 100, 1),
        "min_coverage_pct": int(MIN_DATA_COVERAGE * 100),
        "critical_symbols": CRITICAL_SYMBOLS,
        "critical_missing": critical_missing,
        "critical_history_requirements": CRITICAL_HISTORY_REQUIREMENTS,
        "critical_history_missing": critical_history_missing,
        "sector_history_valid": sector_history_valid,
        "sector_history_required": MIN_SECTOR_HISTORY_SYMBOLS,
        "sector_history_min_points": MIN_SECTOR_HISTORY_POINTS,
        "message": message,
    }


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
    ma20  = simple_ma(closes, 20)
    ma50  = simple_ma(closes, 50)
    ma200 = simple_ma(closes, 200)
    return {
        "ma20":   round(ma20,  4) if ma20  is not None else None,
        "ma50":   round(ma50,  4) if ma50  is not None else None,
        "ma200":  round(ma200, 4) if ma200 is not None else None,
        "rsi14":  wilder_rsi(closes, 14),
        "pctile": percentile_1y(closes),
    }


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(v)))


_SOURCE_NAMES = {"yahoo": "Yahoo", "stooq": "Stooq",
                 "coingecko": "CoinGecko", "binance": "Binance"}

def _src_label(q: dict | None) -> str:
    if not q:
        return "Yahoo"
    return _SOURCE_NAMES.get((q.get("source") or "yahoo").lower(), "Yahoo")


def pct(q, key="changePct"):
    return (q.get(key) or 0) if q else 0


def price(q):
    return q.get("price") if q else None


def ema(closes: list[float], n: int) -> list[float]:
    """Return full EMA series. Seeded with the first n-period SMA."""
    if len(closes) < n:
        return []
    k = 2.0 / (n + 1)
    series = [sum(closes[:n]) / n]
    for c in closes[n:]:
        series.append(series[-1] * (1 - k) + c * k)
    return series


def macd(closes: list[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> dict | None:
    """MACD(fast, slow, signal). Returns None if insufficient data."""
    if len(closes) < slow + signal:
        return None
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    diff = len(fast_ema) - len(slow_ema)
    macd_line = [f - s for f, s in zip(fast_ema[diff:], slow_ema)]
    if len(macd_line) < signal:
        return None
    sig_ema = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line[-len(sig_ema):], sig_ema)]
    return {
        "macd_line":      round(macd_line[-1], 3),
        "signal_line":    round(sig_ema[-1], 3),
        "histogram":      round(histogram[-1], 3),
        "prev_histogram": round(histogram[-2], 3) if len(histogram) >= 2 else None,
    }


def compute_sector_rs(sector_histories: dict) -> list[dict]:
    """Rank sectors by blended 1M + 3M momentum (RS score). Sorted best-first."""
    results = []
    for sym, closes in sector_histories.items():
        if len(closes) < 22:
            continue
        cur  = closes[-1]
        m1   = (cur / closes[-22] - 1) * 100 if len(closes) >= 22 else 0
        m3   = (cur / closes[-64] - 1) * 100 if len(closes) >= 64 else m1
        rs   = round(0.4 * m1 + 0.6 * m3, 2)
        results.append({
            "symbol":    sym,
            "name":      SECTOR_NAMES.get(sym, sym),
            "rs_score":  rs,
            "return_1m": round(m1, 2),
            "return_3m": round(m3, 2),
        })
    results.sort(key=lambda x: x["rs_score"], reverse=True)
    return results


def atr14(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> float | None:
    """Wilder-smoothed ATR(n). Requires at least n+1 data points."""
    if len(closes) < n + 1 or len(highs) < n + 1 or len(lows) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr


def bb_width(closes: list[float], period: int = 20, mult: float = 2.0) -> float | None:
    """Bollinger Band Width = (upper - lower) / middle, as a ratio."""
    data = [c for c in closes[-period:] if c is not None]
    if len(data) < period:
        return None
    mid = sum(data) / period
    if mid == 0:
        return None
    std = (sum((c - mid) ** 2 for c in data) / period) ** 0.5
    return (2 * mult * std) / mid


def classify_market_character(closes: list[float], highs: list[float], lows: list[float]) -> dict:
    """Classify recent market regime: Trending / Choppy / Extended / Mixed."""
    if not closes or not highs or not lows:
        return {"label": "Unknown", "color": "gray", "atr_pct": None, "bbw_pct": None}
    cur = closes[-1]
    atr_val = atr14(highs, lows, closes)
    atr_pct = round(atr_val / cur * 100, 2) if (atr_val and cur) else None
    bbw = bb_width(closes)
    bbw_pct = round(bbw * 100, 2) if bbw is not None else None
    rsi = wilder_rsi(closes, 14)

    if atr_pct is not None and bbw_pct is not None:
        if rsi and rsi > CHAR_RSI_EXTENDED:
            label, color = "Extended", "red"
        elif atr_pct > CHAR_ATR_TRENDING and bbw_pct > CHAR_BBW_TRENDING:
            label, color = "Trending", "green"
        elif atr_pct < CHAR_ATR_CHOPPY or bbw_pct < CHAR_BBW_CHOPPY:
            label, color = "Choppy", "orange"
        else:
            label, color = "Mixed", "yellow"
    else:
        label, color = "Unknown", "gray"

    return {"label": label, "color": color, "atr_pct": atr_pct, "bbw_pct": bbw_pct}


# ─── pillar 1 — volatility ─────────────────────────────────────────────────
def score_volatility(quotes: dict, vix_closes: list[float]) -> PillarResult:
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
    if   vix_val < VIX_CALM:     d, lbl, col = +35, "Low",      "green"
    elif vix_val < VIX_MODERATE: d, lbl, col = +25, "Moderate", "yellow"
    elif vix_val < VIX_ELEVATED: d, lbl, col = +10, "Elevated", "orange"
    elif vix_val < VIX_HIGH:     d, lbl, col = -10, "High",     "red"
    else:                        d, lbl, col = -30, "Extreme",  "red"
    score += d
    reasons.append(f"{'+' if d>=0 else ''}{d} VIX {vix_val:.2f} → {lbl}")
    details.update(vix_level=round(vix_val, 2), vix_label=lbl, vix_color=col)

    # VIX trend
    vix_chg = pct(vix_q)
    if   vix_chg < -VIX_TREND_BIG: d, lbl, col = +12, "Falling", "green"
    elif vix_chg <  0:              d, lbl, col = +5,  "Calming", "green"
    elif vix_chg <  VIX_TREND_BIG: d, lbl, col = -5,  "Rising",  "orange"
    else:                           d, lbl, col = -15, "Spiking", "red"
    score += d
    reasons.append(f"{'+' if d>=0 else ''}{d} VIX {lbl} ({vix_chg:+.2f}%)")
    details.update(vix_trend=lbl, vix_trend_color=col, vix_change_pct=round(vix_chg, 2))

    # VIX 1Y percentile — require ≥20 data points; single-value fallback gives misleading 0th %ile
    vix_1y = [c for c in (vix_closes or []) if c is not None]
    if len(vix_1y) >= 20:
        vix_pct = round(len([c for c in vix_1y if c < vix_val]) / len(vix_1y) * 100)
        if   vix_pct < VIX_PCTILE_LOW:  score += 5;  reasons.append(f"+5 VIX at {vix_pct}th %ile (calm zone)")
        elif vix_pct > VIX_PCTILE_HIGH: score -= 10; reasons.append(f"-10 VIX at {vix_pct}th %ile (fear zone)")
        details["vix_pctile"] = vix_pct
    else:
        details["vix_pctile"] = None

    # Flow Sentiment proxy — TQQQ/SQQQ net + UVXY fear. NOT a put/call ratio;
    # we display an honest "Flow Sentiment" 0-100 score instead of fake P/C number.
    bull = pct(tqqq_q)
    bear = pct(sqqq_q)
    uvxy = pct(uvxy_q)
    net = bull - bear

    if   net > FLOW_NET_STRONG_BULL: flow, flbl, fcol = 85, "Strong Risk-On",  "green"
    elif net > FLOW_NET_BULL:        flow, flbl, fcol = 70, "Risk-On",         "green"
    elif net > FLOW_NET_MILD_BULL:   flow, flbl, fcol = 55, "Tilting Bullish", "yellow"
    elif net > FLOW_NET_MILD_BEAR:   flow, flbl, fcol = 45, "Neutral",         "yellow"
    elif net > FLOW_NET_BEAR:        flow, flbl, fcol = 30, "Tilting Bearish", "orange"
    else:                            flow, flbl, fcol = 15, "Risk-Off",        "red"

    if uvxy > UVXY_FEAR_THRESHOLD:  flow -= 10
    if uvxy < -UVXY_FEAR_THRESHOLD: flow += 8
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
        if ratio > VIX_TERM_BACKW:
            d, vix_term_label, vix_term_color = -10, "Backwardation", "red"
            score += d
            reasons.append(f"{d} VIX/VIX3M {ratio:.2f}x — fear spike, backwardation")
        elif ratio < VIX_TERM_STEEP:
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

    # VIX9D/VIX ratio — near-term vs. 30-day fear premium (free P/C proxy)
    # VIX9D > VIX: near-term fear spike, hedging demand elevated → bearish
    # VIX9D << VIX: near-term calm, complacency or resolved event → bullish
    vix9d_q = quotes.get("^VIX9D")
    vix9d_val = price(vix9d_q)
    vix9d_ratio, vix9d_label, vix9d_color = None, "N/A", "gray"
    if vix_val and vix9d_val and vix_val > 0:
        vix9d_ratio = round(vix9d_val / vix_val, 3)
        if vix9d_ratio > VIX9D_FEAR:
            d, vix9d_label, vix9d_color = -12, "Fear Spike", "red"
            score += d
            reasons.append(f"{d} VIX9D/VIX {vix9d_ratio:.2f}x — near-term fear elevated")
        elif vix9d_ratio < VIX9D_CALM:
            d, vix9d_label, vix9d_color = +6, "Calm", "green"
            score += d
            reasons.append(f"+{d} VIX9D/VIX {vix9d_ratio:.2f}x — near-term calm, event risk low")
        else:
            vix9d_label, vix9d_color = "Neutral", "yellow"
            reasons.append(f"+0 VIX9D/VIX {vix9d_ratio:.2f}x — near-term neutral")
    details.update(
        vix9d_value=round(vix9d_val, 2) if vix9d_val else None,
        vix9d_ratio=vix9d_ratio, vix9d_label=vix9d_label, vix9d_color=vix9d_color,
    )

    # SKEW Index — context-aware interpretation.
    # High SKEW alone ≠ bearish: institutions often buy OTM puts while staying long ("wall of worry").
    # Only treat high SKEW as a bearish signal when VIX is also elevated — that is compound fear.
    # Low SKEW = no crash protection demand = dangerous complacency = slight negative.
    skew_q = quotes.get("^SKEW")
    skew_val = price(skew_q)
    skew_label, skew_color = "N/A", "gray"
    vix_calm = vix_val < VIX_MODERATE  # VIX < 19 = calm environment
    if skew_val:
        if skew_val >= SKEW_EXTREME:  # >= 150
            if vix_calm:
                # Institutions buying crash insurance while staying long = wall of worry (bullish lean)
                d, skew_label, skew_color = +2, "Cautious Optimism", "yellow"
                score += d
                reasons.append(f"+{d} SKEW {skew_val:.0f} + calm VIX — hedged longs, wall of worry (not panic)")
            else:
                # High SKEW + elevated VIX = compound fear signal = bearish
                d, skew_label, skew_color = -10, "Compound Fear", "red"
                score += d
                reasons.append(f"{d} SKEW {skew_val:.0f} + elevated VIX — compound fear signal")
        elif skew_val >= SKEW_ELEVATED:  # 140–149
            if vix_calm:
                # Elevated hedging with calm vol = cautious bulls, healthy wall-of-worry
                d, skew_label, skew_color = +3, "Cautious Bulls", "green"
                score += d
                reasons.append(f"+{d} SKEW {skew_val:.0f} + calm VIX — cautious bulls long with insurance")
            else:
                # Elevated hedging + rising vol = genuine tail-risk concern
                d, skew_label, skew_color = -5, "Elevated Hedging", "orange"
                score += d
                reasons.append(f"{d} SKEW {skew_val:.0f} + elevated VIX — elevated tail hedging with rising vol")
        elif skew_val >= SKEW_NORMAL:  # 120–139
            skew_label, skew_color = "Normal", "yellow"
            reasons.append(f"+0 SKEW {skew_val:.0f} — normal tail risk appetite")
        else:  # < 120
            # Low SKEW = nobody buying crash protection = complacency risk
            d, skew_label, skew_color = -3, "Complacent", "orange"
            score += d
            reasons.append(f"{d} SKEW {skew_val:.0f} — low tail protection demand, complacency risk")
    details.update(
        skew_value=round(skew_val, 1) if skew_val else None,
        skew_label=skew_label, skew_color=skew_color,
    )

    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 2 — trend ──────────────────────────────────────────────────────
def score_trend(quotes: dict, spy_closes: list[float], qqq_closes: list[float],
                spy_ohlcv: dict | None = None) -> PillarResult:
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
        if rsi >= RSI_SEVERELY_OVERBOUGHT:
            score -= 15
            reasons.append(f"-15 RSI {rsi} — severely overbought, high mean-reversion risk, don't chase")
        elif rsi >= RSI_OVERBOUGHT:
            score -= 8
            reasons.append(f"-8 RSI {rsi} — overbought, wait for pullback to 20d before entry")
        elif rsi <= RSI_OVERSOLD:
            score += 5
            reasons.append(f"+5 RSI {rsi} — oversold, bounce candidate")
        elif RSI_SWEET_SPOT_LOW <= rsi <= RSI_SWEET_SPOT_HIGH:
            score += 5
            reasons.append(f"+5 RSI {rsi} — sweet spot, ideal swing entry zone after pullback")

    spy_1y_hi = max(spy_closes[-252:]) if len(spy_closes) >= 252 else (max(spy_closes) if spy_closes else spy_px or 1)
    ath_dist = round((spy_px / spy_1y_hi - 1) * 100, 1) if spy_px and spy_1y_hi else 0

    # Volume confirmation — SPY volume vs. 20-day average
    vol_ratio, vol_label, vol_color = None, "N/A", "gray"
    if spy_ohlcv and spy_ohlcv.get("volumes"):
        vols = [v for v in spy_ohlcv["volumes"] if v and v > 0]
        if len(vols) >= 21:
            avg_vol = sum(vols[-21:-1]) / 20   # 20-day avg, excluding today
            today_vol = vols[-1]
            vol_ratio = round(today_vol / avg_vol, 2)
            spy_chg_val = pct(spy_q)
            if vol_ratio >= VOL_HIGH_RATIO and spy_chg_val > 0:
                d, vol_label, vol_color = +8, "High-Vol Rally", "green"
                score += d
                reasons.append(f"+{d} Volume {vol_ratio:.1f}x avg — confirming rally")
            elif vol_ratio >= VOL_HIGH_RATIO and spy_chg_val < 0:
                d, vol_label, vol_color = -8, "High-Vol Selloff", "red"
                score += d
                reasons.append(f"{d} Volume {vol_ratio:.1f}x avg — confirming selloff")
            elif vol_ratio < VOL_LOW_RATIO:
                d, vol_label, vol_color = -3, "Low Volume", "orange"
                score += d
                reasons.append(f"{d} Volume {vol_ratio:.1f}x avg — low conviction")
            else:
                vol_label, vol_color = "Normal", "yellow"
                reasons.append(f"+0 Volume {vol_ratio:.1f}x avg — normal")

    # Market character (ATR + Bollinger Band Width)
    char_label, char_color, char_atr_pct, char_bbw_pct = "N/A", "gray", None, None
    if spy_ohlcv and spy_ohlcv.get("highs") and spy_ohlcv.get("lows") and spy_closes:
        char = classify_market_character(spy_closes, spy_ohlcv["highs"], spy_ohlcv["lows"])
        char_label    = char["label"]
        char_color    = char["color"]
        char_atr_pct  = char.get("atr_pct")
        char_bbw_pct  = char.get("bbw_pct")
        if char_label == "Choppy":
            score -= 5
            reasons.append("-5 Market character: Choppy — elevated false-breakout risk")
        elif char_label == "Extended":
            score -= 8
            reasons.append("-8 Market character: Extended — mean-reversion risk")
        elif char_label == "Trending":
            reasons.append("+0 Market character: Trending — directional bias intact")

    # MACD(12,26,9) on SPY — momentum crossover signal
    macd_d = macd(spy_closes) if spy_closes else None
    macd_line_val = signal_val = hist_val = prev_hist = None
    macd_label, macd_color = "N/A", "gray"
    if macd_d:
        macd_line_val = macd_d["macd_line"]
        signal_val    = macd_d["signal_line"]
        hist_val      = macd_d["histogram"]
        prev_hist     = macd_d.get("prev_histogram")
        bull = macd_line_val > signal_val
        hist_expanding = (prev_hist is not None and
                          ((hist_val > 0 and hist_val > prev_hist) or
                           (hist_val < 0 and hist_val < prev_hist)))
        if bull and macd_line_val > 0:
            d, macd_label, macd_color = +10, "Bullish (above 0)", "green"
        elif bull and macd_line_val <= 0:
            d, macd_label, macd_color = +5, "Bullish (below 0)", "yellow"
        elif not bull and macd_line_val > 0:
            d, macd_label, macd_color = -5, "Bearish (above 0)", "orange"
        else:
            d, macd_label, macd_color = -10, "Bearish (below 0)", "red"
        if hist_expanding and bull:
            d += 3    # histogram widening = momentum accelerating
        score += d
        reasons.append(f"{'+' if d>=0 else ''}{d} MACD {macd_line_val:.2f}/Signal {signal_val:.2f} — {macd_label}")

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
        "vol_ratio": vol_ratio, "vol_label": vol_label, "vol_color": vol_color,
        "char_label": char_label, "char_color": char_color,
        "char_atr_pct": char_atr_pct, "char_bbw_pct": char_bbw_pct,
        "macd_line": macd_line_val, "macd_signal": signal_val,
        "macd_hist": hist_val, "macd_label": macd_label, "macd_color": macd_color,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 3 — breadth ────────────────────────────────────────────────────
def score_breadth(quotes: dict, rsp_closes: list[float],
                  sector_histories: dict | None = None) -> PillarResult:
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

    # Sector ETF % above 200d MA — structural breadth health
    n_above_200, n_sec_valid = 0, 0
    sector_above_200_data = {}
    if sector_histories:
        for sym in SECTOR_SYMBOLS:
            closes = sector_histories.get(sym, [])
            if len(closes) >= 150:
                ma200 = simple_ma(closes, 200) if len(closes) >= 200 else simple_ma(closes, len(closes))
                above = bool(ma200 and closes[-1] > ma200)
                sector_above_200_data[sym] = above
                n_sec_valid += 1
                if above:
                    n_above_200 += 1
    pct_above_200 = round(n_above_200 / n_sec_valid * 100) if n_sec_valid else None
    if pct_above_200 is not None:
        if pct_above_200 >= BREADTH_ABOVE200_BULL:
            score += 10
            reasons.append(f"+10 {n_above_200}/{n_sec_valid} sectors above 200d MA — broad bull")
        elif pct_above_200 <= BREADTH_ABOVE200_WEAK:
            score -= 10
            reasons.append(f"-10 Only {n_above_200}/{n_sec_valid} sectors above 200d MA — structural weakness")

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
        "sectors_above_200": n_above_200,
        "sectors_above_200_total": n_sec_valid,
        "pct_sectors_above_200": pct_above_200,
        "sector_above_200_data": sector_above_200_data,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 4 — momentum ───────────────────────────────────────────────────
def score_momentum(quotes: dict, sector_histories: dict | None = None) -> PillarResult:
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

    # Sector Relative Strength (1M + 3M blended momentum ranking)
    # Shows where institutional money is rotating, not just what moved today.
    sector_rs_list = []
    rs_rotation_label, rs_rotation_color = "N/A", "gray"
    if sector_histories:
        sector_rs_list = compute_sector_rs(sector_histories)
        if len(sector_rs_list) >= 3:
            leaders_syms  = {r["symbol"] for r in sector_rs_list[:3]}
            laggards_syms = {r["symbol"] for r in sector_rs_list[-3:]}
            cyclicals  = {"XLY", "XLF", "XLK", "XLE", "XLI"}
            defensives = {"XLU", "XLP", "XLV"}
            n_cyc_lead = len(leaders_syms & cyclicals)
            n_def_lead = len(leaders_syms & defensives)
            if n_cyc_lead >= 2:
                d, rs_rotation_label, rs_rotation_color = +5, "Cyclical Leadership", "green"
                score += d
                reasons.append(f"+{d} Sector RS: cyclicals leading — risk-on rotation")
            elif n_def_lead >= 2:
                d, rs_rotation_label, rs_rotation_color = -5, "Defensive Rotation", "red"
                score += d
                reasons.append(f"{d} Sector RS: defensives leading — risk-off rotation")
            else:
                rs_rotation_label, rs_rotation_color = "Mixed Rotation", "yellow"

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
        "sector_rs": sector_rs_list,
        "rs_rotation_label": rs_rotation_label, "rs_rotation_color": rs_rotation_color,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── pillar 5 — macro ──────────────────────────────────────────────────────
def score_macro(quotes: dict, tnx_closes: list[float], dxy_closes: list[float],
                btc_q: dict | None, btc_closes: list[float], fomc: dict,
                hyg_closes: list[float] | None = None,
                lqd_closes: list[float] | None = None,
                opex: dict | None = None, season: dict | None = None) -> PillarResult:
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

    # HYG-LQD Spread — credit quality divergence (liquidity early-warning).
    # When HYG (junk bonds) underperforms LQD (investment-grade bonds),
    # smart money is fleeing risky credit — often signals stress before equities react.
    lqd_q = quotes.get("LQD")
    hyg_lqd_label, hyg_lqd_color = "N/A", "gray"
    hyg_lqd_spread_today = None
    hyg_lqd_20d_spread   = None
    if hyg_q and lqd_q:
        hyg_chg_now = pct(hyg_q)
        lqd_chg_now = pct(lqd_q)
        hyg_lqd_spread_today = round(hyg_chg_now - lqd_chg_now, 3)

        # 20-day rolling return divergence — structural signal
        if (hyg_closes and lqd_closes and
                len(hyg_closes) >= 21 and len(lqd_closes) >= 21 and
                hyg_closes[-21] > 0 and lqd_closes[-21] > 0):   # guard against zero prices
            hyg_20d = (hyg_closes[-1] / hyg_closes[-21] - 1) * 100
            lqd_20d = (lqd_closes[-1] / lqd_closes[-21] - 1) * 100
            hyg_lqd_20d_spread = round(hyg_20d - lqd_20d, 2)
        else:
            hyg_lqd_20d_spread = None

        structural_stress  = hyg_lqd_20d_spread is not None and hyg_lqd_20d_spread < -2.0
        structural_risk_on = hyg_lqd_20d_spread is not None and hyg_lqd_20d_spread > 2.0
        intraday_stress    = hyg_lqd_spread_today < -0.3
        intraday_risk_on   = hyg_lqd_spread_today > 0.3

        if structural_stress and intraday_stress:
            d, hyg_lqd_label, hyg_lqd_color = -12, "Credit Stress", "red"
            score += d
            reasons.append(
                f"{d} HYG-LQD: {hyg_lqd_spread_today:+.2f}% today, "
                f"{hyg_lqd_20d_spread:+.1f}% 20d — credit quality deteriorating")
        elif structural_stress:
            d, hyg_lqd_label, hyg_lqd_color = -6, "Credit Deteriorating", "orange"
            score += d
            reasons.append(
                f"{d} HYG-LQD: {hyg_lqd_20d_spread:+.1f}% 20d divergence — junk lagging IG")
        elif intraday_stress:
            d, hyg_lqd_label, hyg_lqd_color = -5, "Spread Widening", "orange"
            score += d
            reasons.append(
                f"{d} HYG-LQD: {hyg_lqd_spread_today:+.2f}% today — acute credit spread widening")
        elif structural_risk_on:
            d, hyg_lqd_label, hyg_lqd_color = +5, "Credit Risk-On", "green"
            score += d
            reasons.append(
                f"+{d} HYG-LQD: {hyg_lqd_20d_spread:+.1f}% 20d — junk outperforming IG, risk appetite healthy")
        elif intraday_risk_on:
            d, hyg_lqd_label, hyg_lqd_color = +3, "Intraday Risk-On", "green"
            score += d
            reasons.append(
                f"+{d} HYG-LQD: {hyg_lqd_spread_today:+.2f}% today — junk outperforming IG intraday")
        else:
            hyg_lqd_label, hyg_lqd_color = "Neutral", "yellow"
            reasons.append(f"+0 HYG-LQD: {hyg_lqd_spread_today:+.2f}% today — credit spread neutral")
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

    # Yield Curve — 3-month T-bill (^IRX) vs 10-year Treasury (^TNX)
    # Inversion (short > long) historically precedes recessions and bear markets.
    irx_q   = quotes.get("^IRX")
    irx_val = price(irx_q)
    curve_spread = None
    curve_label, curve_color = "N/A", "gray"
    if tnx_val and irx_val:
        curve_spread = round(tnx_val - irx_val, 2)
        if   curve_spread < -0.5:
            d, curve_label, curve_color = -15, "Deeply Inverted", "red"
            score += d
            reasons.append(f"{d} Yield curve {curve_spread:+.2f}% — deep inversion, recession watch")
        elif curve_spread < 0:
            d, curve_label, curve_color = -8, "Inverted", "red"
            score += d
            reasons.append(f"{d} Yield curve {curve_spread:+.2f}% — inverted, elevated risk")
        elif curve_spread < 0.5:
            curve_label, curve_color = "Flat", "orange"
            reasons.append(f"+0 Yield curve {curve_spread:+.2f}% — flat, watch for inversion")
        elif curve_spread < 1.5:
            d, curve_label, curve_color = +5, "Normal", "yellow"
            score += d
            reasons.append(f"+{d} Yield curve {curve_spread:+.2f}% — normal slope")
        else:
            d, curve_label, curve_color = +8, "Steep", "green"
            score += d
            reasons.append(f"+{d} Yield curve {curve_spread:+.2f}% — steep curve, growth priced in")

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

    # Options Expiration — gamma pinning, false breakouts, vol squeezes near OpEx
    opex_days = opex.get("days_until") if opex else None
    if opex_days is not None:
        if opex_days == 0:
            score -= 5
            reasons.append(f"-5 {opex.get('kind', 'OpEx')} today — gamma pinning, use caution")
        elif opex_days <= 2:
            score -= 3
            reasons.append(f"-3 {opex.get('kind', 'OpEx')} in {opex_days}d — approaching expiration")

    # Seasonality — monthly historical bias (weak signal, small adjustment)
    season_adj = season.get("score_adj", 0) if season else 0
    if season and season_adj != 0:
        score += season_adj
        reasons.append(f"{'+' if season_adj>=0 else ''}{season_adj} Seasonality: {season.get('label')} — {season.get('bias')}")

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
        "hyg_lqd_spread_today": hyg_lqd_spread_today,
        "hyg_lqd_20d_spread":   hyg_lqd_20d_spread,
        "hyg_lqd_label": hyg_lqd_label, "hyg_lqd_color": hyg_lqd_color,
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
        "irx_value": round(irx_val, 3) if irx_val else None,
        "curve_spread": curve_spread,
        "curve_label": curve_label, "curve_color": curve_color,
        "opex_days": opex_days,
        "opex_date": opex.get("date_pretty") if opex else None,
        "opex_label": opex.get("label") if opex else "N/A",
        "opex_color": opex.get("color") if opex else "gray",
        "opex_kind":  opex.get("kind") if opex else None,
        "season_label": season.get("label") if season else "N/A",
        "season_bias":  season.get("bias") if season else "N/A",
        "season_color": season.get("color") if season else "gray",
        "season_adj":   season_adj,
    }
    return {"score": clamp(score), "details": details, "reasons": reasons}


# ─── conflict detector ─────────────────────────────────────────────────────
#
# Two-tier design:
#   1. Signal-level checks  — need specific named values deep inside pillar
#      details (e.g. vix9d_label, macd_label). Stay as if-statements because
#      the conditions don't reduce to simple score comparisons.
#   2. Pillar divergence table — compare two pillar *scores* against thresholds.
#      Fully declarative: adding a new divergence = one line in PILLAR_DIVERGENCES.
#
# ── Pillar divergence rules ────────────────────────────────────────────────
# Each entry: (strong_pillar, min_score, weak_pillar, max_score,
#              title, detail, severity)
# Fires when strong_pillar >= min_score AND weak_pillar <= max_score.
PILLAR_DIVERGENCES = [
    ("trend", 85, "momentum", 45,
     "Strong Trend + Weak Participation",
     "SPY price structure intact but only a handful of sectors participating — "
     "narrow rallies are fragile. Index strength is not market strength. "
     "Don't add new longs; let winners run but don't chase.",
     "warning"),

    ("trend", 85, "breadth", 40,
     "Strong Trend + Breadth Breakdown",
     "Price trend holding while sector breadth deteriorates — classic distribution phase. "
     "The average stock is already rolling over while the index is held up by mega-caps. "
     "Shorten hold times, tighten stops.",
     "warning"),

    ("trend", 80, "macro", 35,
     "Bull Trend + Macro Headwind",
     "Price structure bullish but macro conditions (yields, credit, dollar) are deteriorating. "
     "Works until it doesn't — trade shorter timeframes and reduce overnight exposure.",
     "caution"),

    ("trend", 80, "volatility", 35,
     "Bull Trend + Elevated Volatility",
     "Price trend bullish but volatility elevated — moves will be sharp in both directions. "
     "Size down even when direction is right. Wide stops eat your edge.",
     "caution"),

    ("volatility", 75, "breadth", 40,
     "Calm Vol + Weak Breadth",
     "VIX is low (complacency zone) but breadth is already weak underneath — "
     "the next volatility spike may be larger than the quiet tape implies.",
     "info"),
]


def detect_conflicts(pillars: dict, total_score: int) -> list[dict]:
    """Find contradicting signals across pillars. Two-tier: signal-level checks
    for specific named values, declarative table for pillar score divergences."""
    tr  = pillars["trend"]["details"]
    vol = pillars["volatility"]["details"]
    mom = pillars["momentum"]["details"]
    mac = pillars["macro"]["details"]

    char       = tr.get("char_label", "")
    regime     = tr.get("regime", "")
    macd_l     = tr.get("macd_label", "")
    vol_l      = tr.get("vol_label", "")
    vix9d_l    = vol.get("vix9d_label", "")
    skew_l     = vol.get("skew_label", "")
    rs_rot     = mom.get("rs_rotation_label", "")
    curve_l    = mac.get("curve_label", "")
    season_adj = mac.get("season_adj", 0)
    season_lbl = mac.get("season_label", "")

    conflicts = []

    # ── 1. Signal-level checks ─────────────────────────────────────────────

    # Overbought market character + bullish MACD
    if char == "Extended" and macd_l.startswith("Bullish"):
        conflicts.append({"title": "Overbought + Bullish Trend MACD",
            "detail": "RSI>72 (Extended character) but MACD still bullish — late-stage momentum, mean-reversion risk is elevated. Consider tighter stops.",
            "severity": "warning"})

    # Near-term fear spike in an uptrend
    if vix9d_l == "Fear Spike" and regime in ("Uptrend", "Recovering"):
        conflicts.append({"title": "VIX9D Fear Spike in Uptrend",
            "detail": "Near-term hedging demand surging despite bullish price trend — a binary risk event (earnings, Fed, geopolitical) may be approaching.",
            "severity": "warning"})

    # Defensive sector rotation while price trend is bullish
    if rs_rot == "Defensive Rotation" and regime in ("Uptrend", "Recovering"):
        conflicts.append({"title": "Defensive RS Rotation in Bull Trend",
            "detail": "Institutional RS flowing into XLU/XLP/XLV while price trend remains intact — potential early distribution. Smart money may be rotating out.",
            "severity": "warning"})

    # High-volume selloff in an uptrend
    if vol_l == "High-Vol Selloff" and regime in ("Uptrend", "Recovering"):
        conflicts.append({"title": "High-Volume Selloff in Uptrend",
            "detail": "Conviction selling while trend is technically intact — possible distribution or key support test. Don't add longs on this bar.",
            "severity": "warning"})

    # Elevated tail-risk hedging + bullish MACD
    if skew_l in ("Elevated", "Extreme Tail Risk") and macd_l.startswith("Bullish"):
        conflicts.append({"title": "Elevated SKEW + Bullish Trend MACD",
            "detail": "Institutions buying OTM puts while SPY's price MACD reads bullish — they may be hedging existing longs, not predicting a top, but the insurance cost is high.",
            "severity": "info"})

    # Inverted yield curve at a positive score
    if curve_l in ("Inverted", "Deeply Inverted") and total_score >= 55:
        conflicts.append({"title": "Inverted Yield Curve",
            "detail": "3M-10Y spread is negative — historically precedes recessions by 6–18 months. Near-term trading may still work but reduce position timeframe and size.",
            "severity": "caution"})

    # Seasonal headwind + intact uptrend
    if season_adj <= -5 and regime == "Uptrend":
        conflicts.append({"title": f"Seasonal Headwind ({season_lbl}) + Uptrend",
            "detail": "Historically weak period but price trend is intact. Seasonality is a low-weight signal — don't fight the trend, but stay alert for the first sign of weakness.",
            "severity": "info"})

    # ── 2. Pillar divergence checks (declarative table) ────────────────────
    scores = {k: pillars[k]["score"] for k in pillars}
    for strong_k, strong_min, weak_k, weak_max, title, detail, severity in PILLAR_DIVERGENCES:
        if scores.get(strong_k, 0) >= strong_min and scores.get(weak_k, 100) <= weak_max:
            conflicts.append({"title": title, "detail": detail, "severity": severity})

    return conflicts


# ─── orchestrator ──────────────────────────────────────────────────────────
def _safe_pillar(fn, *args, name: str = "?") -> dict:
    """Call a pillar scorer; return neutral fallback on exception."""
    try:
        return fn(*args)
    except Exception as e:
        logger.warning("Pillar '%s' raised: %s", name, e)
        return {
            "score": 50,
            "details": {},
            "reasons": [f"⚠ {name} data unavailable — neutral 50"],
        }


def _fetch_instruments() -> dict:
    """Fire all network requests in one concurrent batch; return raw data."""
    all_symbols   = CORE_SYMBOLS + SECTOR_SYMBOLS + INDUSTRY_SYMBOLS
    history_pairs = ([("SPY", 220), ("QQQ", 220), ("RSP", 220),
                      ("^VIX", 252), ("^TNX", 60), ("DX-Y.NYB", 60),
                      ("HYG", 60), ("LQD", 60)]
                     + [(s, 220) for s in SECTOR_SYMBOLS])

    with _TPE(max_workers=24) as ex:
        q_futs           = {ex.submit(get_quote,   s):    s for s in all_symbols}
        h_futs           = {ex.submit(get_history, s, d): s for s, d in history_pairs}
        spy_ohlcv_f      = ex.submit(get_ohlcv, "SPY", 220)
        btc_q_f          = ex.submit(btc_quote)
        btc_h_f          = ex.submit(btc_history)
        fng_s_f          = ex.submit(fetch_fear_greed_stock)
        fng_c_f          = ex.submit(fetch_fear_greed_crypto)
        fut_tape_f       = ex.submit(fetch_futures_tape)
        spy_last_bar_f   = ex.submit(yf_last_bar_date, "SPY", 220)

    def _safe_result(fut, default):
        try:
            return fut.result()
        except Exception:
            logger.debug("Future result error", exc_info=True)
            return default

    return {
        "all_symbols":   all_symbols,
        "quotes":        {q_futs[f]: _safe_result(f, None) for f in q_futs},
        "histories":     {h_futs[f]: _safe_result(f, []) for f in h_futs},
        "spy_ohlcv":     _safe_result(spy_ohlcv_f, None),
        "btc_q":         _safe_result(btc_q_f, None),
        "btc_closes":    _safe_result(btc_h_f, []),
        "fng_stock":     _safe_result(fng_s_f, {"available": False}),
        "fng_crypto":    _safe_result(fng_c_f, {"available": False}),
        "futures_tape":      _safe_result(fut_tape_f, {"valid": False}),
        "spy_last_bar_date": _safe_result(spy_last_bar_f, None),
    }


def vol_target_exposure(closes: list[float]) -> VolTargetInfo | None:
    """Evidence-backed exposure dial: clamp(VOL_TARGET_K / realized vol, 0..100%).

    closes: chronological adjusted closes (most recent last); needs at least
    VOL_TARGET_WINDOW + 1 points. Returns None when history is insufficient,
    contains non-positive prices, or volatility is zero. Vol units match the
    backtest calibration: PERCENT daily returns (see config.VOL_TARGET_K).
    """
    if not closes or len(closes) < VOL_TARGET_WINDOW + 1:
        return None
    tail = closes[-(VOL_TARGET_WINDOW + 1):]
    if any(c is None or c <= 0 for c in tail):
        return None
    rets = [(tail[i] / tail[i - 1] - 1) * 100 for i in range(1, len(tail))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol = var ** 0.5
    if vol <= 0:
        return None
    exposure = min(100.0, max(0.0, 100.0 * VOL_TARGET_K / vol))
    return {"exposure_pct": round(exposure, 1), "realized_vol_pct": round(vol, 2)}


def _day_streak(closes: list[float]) -> dict:
    """Count consecutive trading days SPY closed in the same direction.

    Walks backwards from the most recent bar.  The 'days' count is the
    length of the current run (e.g. 5 consecutive up closes → 5).
    Returns {"days": int, "direction": "up" | "down" | "flat"}.
    """
    if len(closes) < 2:
        return {"days": 0, "direction": "flat"}
    last, prev = closes[-1], closes[-2]
    if last > prev:
        direction = "up"
    elif last < prev:
        direction = "down"
    else:
        return {"days": 0, "direction": "flat"}

    count = 0
    for i in range(len(closes) - 1, 0, -1):
        if direction == "up"   and closes[i] > closes[i - 1]:
            count += 1
        elif direction == "down" and closes[i] < closes[i - 1]:
            count += 1
        else:
            break
    return {"days": count, "direction": direction}


def _splice_live(closes: list[float], live_price: float | None,
                 quote_date: date | None = None,
                 last_bar_date: date | None = None) -> list[float]:
    """Replace (or append) the live quote onto the daily history closes array.

    Normally replaces closes[-1] — Yahoo includes today's partial bar during
    market hours and we overwrite it with a fresher live price.

    After the close Yahoo drops the partial bar before committing the official
    EOD close (typically 4 PM–midnight ET).  During that window quote_date
    (the date of the last trade) is newer than last_bar_date (the date of the
    last history bar), so we append instead of replace.  This ensures the
    streak counter compares today's close against yesterday's, not against
    two days ago.

    On weekends/holidays the last trade date equals the last bar date, so
    the regular replace path is taken and no duplicate bar is introduced.
    """
    if not closes or live_price is None:
        return closes
    if quote_date is not None and last_bar_date is not None and quote_date > last_bar_date:
        return [*closes, live_price]
    return [*closes[:-1], live_price]


def _run_pillars(instruments: dict) -> dict[str, dict]:
    """Run all 5 pillar scorers against the fetched instrument data."""
    quotes   = instruments["quotes"]
    hist     = instruments["histories"]
    sector_h = {s: hist.get(s, []) for s in SECTOR_SYMBOLS}

    def _live(sym: str) -> float | None:
        q = quotes.get(sym)
        return price(q) if q else None

    # Splice the live quote as the current bar so close-based indicators
    # (MA, RSI) reflect the actual price right now, not the 5-min-stale
    # cached daily close.  ATR uses highs/lows from spy_ohlcv which is not
    # spliced here (intraday OHLC would require a separate tick fetch).
    vix_hist = _splice_live(hist.get("^VIX",     []), _live("^VIX"))
    spy_hist = _splice_live(hist.get("SPY",       []), _live("SPY"))
    qqq_hist = _splice_live(hist.get("QQQ",       []), _live("QQQ"))
    rsp_hist = _splice_live(hist.get("RSP",       []), _live("RSP"))
    tnx_hist = _splice_live(hist.get("^TNX",      []), _live("^TNX"))
    dxy_hist = _splice_live(hist.get("DX-Y.NYB",  []), _live("DX-Y.NYB"))
    hyg_hist = _splice_live(hist.get("HYG",       []), _live("HYG"))
    lqd_hist = _splice_live(hist.get("LQD",       []), _live("LQD"))
    btc_hist = _splice_live(
        instruments["btc_closes"],
        price(instruments["btc_q"]) if instruments.get("btc_q") else None,
    )
    spliced_sector_h = {s: _splice_live(hist.get(s, []), _live(s)) for s in SECTOR_SYMBOLS}

    vol  = _safe_pillar(score_volatility, quotes, vix_hist, name="Volatility")
    tr   = _safe_pillar(score_trend, quotes, spy_hist, qqq_hist,
                        instruments["spy_ohlcv"], name="Trend")
    br   = _safe_pillar(score_breadth, quotes, rsp_hist, spliced_sector_h, name="Breadth")
    mom  = _safe_pillar(score_momentum, quotes, spliced_sector_h, name="Momentum")
    mac  = _safe_pillar(score_macro, quotes,
                        tnx_hist, dxy_hist,
                        instruments["btc_q"], btc_hist,
                        instruments["fomc"], hyg_hist, lqd_hist,
                        instruments["opex"], instruments["season"], name="Macro")
    return {"volatility": vol, "trend": tr, "breadth": br, "momentum": mom, "macro": mac}


def _apply_overrides(total: int, pillars: dict, data_quality: dict) -> tuple[int, int, int | None, list[str], str, str, str]:
    """Apply hard regime caps and return (total, raw_total, safety_max_score, override_reasons, decision, color, position)."""
    raw_total = total
    override_reasons: list[str] = []
    safety_max_score = None

    vix_level    = pillars["volatility"]["details"].get("vix_level") or 0
    spy_above_200 = pillars["trend"]["details"].get("above_200", True)

    if data_quality["valid"]:
        if vix_level >= VIX_FLOOR_CRISIS:  # >= 50: extreme crisis
            safety_max_score = 39 if safety_max_score is None else min(safety_max_score, 39)
            if total > 39:
                total = 39
            override_reasons.append(
                f"VIX {vix_level:.0f} ≥ 50 — extreme crisis vol; "
                "if trading, defined-risk only (very small size)"
            )
        elif vix_level >= VIX_FLOOR_HIGH:  # 40–49: serious fear, not a hard NO
            # Historically contains generational entries (Mar 2020, Oct 2022, Oct 2008)
            safety_max_score = 47 if safety_max_score is None else min(safety_max_score, 47)
            if total > 47:
                total = 47
            override_reasons.append(
                f"VIX {vix_level:.0f} ≥ 40 — elevated fear; "
                "trade small with defined risk only on highest-conviction setups"
            )
        elif vix_level >= VIX_FLOOR_MODERATE:  # 35–39: high fear, reduce size
            safety_max_score = 57 if safety_max_score is None else min(safety_max_score, 57)
            if total > 57:
                total = 57
            override_reasons.append(
                f"VIX {vix_level:.0f} ≥ 35 — high fear; reduce position size"
            )

        if not spy_above_200:
            safety_max_score = 54 if safety_max_score is None else min(safety_max_score, 54)
            if total > 54:
                total = 54
            override_reasons.append("SPY below 200d MA - bear market regime, score capped at NO")

    if not data_quality["valid"]:
        total = 0
        safety_max_score = 0
        decision, dc, pos = "DATA UNAVAILABLE", "red", "NO TRADE"
        override_reasons.insert(0, data_quality["message"])
    else:
        decision, dc, pos = decision_for_score(total)

    return total, raw_total, safety_max_score, override_reasons, decision, dc, pos


def _build_ticker(quotes: dict, btc_q: dict | None) -> list:
    ticker: list[dict] = []
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
    return ticker


def compute_dashboard() -> DashboardResult:
    """Orchestrate a full dashboard refresh in four clean phases."""
    # 1. Fetch
    instruments = _fetch_instruments()
    instruments.update({
        "mstate":      market_state(),
        "fomc":        fomc_proximity(),
        "opex":        opex_proximity(),
        "season":      seasonality(),
        "earnings":    earnings_season(),
        "econ_events": econ_proximity(),
    })

    # 2. Score
    pillars      = _run_pillars(instruments)
    quotes       = instruments["quotes"]
    all_symbols  = instruments["all_symbols"]
    requested    = len(all_symbols)
    fetched      = sum(1 for q in quotes.values() if q)
    failed       = [s for s, q in quotes.items() if not q]
    data_quality = build_data_quality(quotes, requested, fetched, failed,
                                      instruments["histories"], SECTOR_SYMBOLS)

    # 3. Aggregate
    raw_total = int(
        pillars["volatility"]["score"] * PILLAR_WEIGHTS["volatility"] +
        pillars["trend"]["score"]      * PILLAR_WEIGHTS["trend"] +
        pillars["breadth"]["score"]    * PILLAR_WEIGHTS["breadth"] +
        pillars["momentum"]["score"]   * PILLAR_WEIGHTS["momentum"] +
        pillars["macro"]["score"]      * PILLAR_WEIGHTS["macro"]
    )
    total, _, safety_max, override_reasons, decision, dc, pos = _apply_overrides(
        raw_total, pillars, data_quality)
    conflicts = detect_conflicts(pillars, total)

    # SPY consecutive-day win/loss streak — uses spliced history so today counts.
    # Pass quote_date vs last_bar_date so _splice_live appends (rather than
    # replacing) when Yahoo drops the partial bar after close (4 PM–midnight ET).
    spy_q = instruments["quotes"].get("SPY")
    spy_closes_spliced = _splice_live(
        instruments["histories"].get("SPY", []),
        price(spy_q),
        quote_date=spy_q.get("trade_date") if spy_q else None,
        last_bar_date=instruments.get("spy_last_bar_date"),
    )
    spy_streak = _day_streak(spy_closes_spliced)

    # 4. Assemble result
    mstate = instruments["mstate"]
    fomc   = instruments["fomc"]
    return {
        "total_score": total,
        "raw_total_score": raw_total,
        "safety_max_score": safety_max,
        "decision": decision, "decision_color": dc, "position_size": pos,
        "action_hint": (action_for_score(total) if data_quality["valid"]
                        else "Exposure off — live market data is unavailable"),
        "market_state": mstate,
        "fomc":         fomc,
        "opex":         instruments["opex"],
        "season":       instruments["season"],
        "earnings":     instruments["earnings"],
        "econ_events":  instruments["econ_events"],
        "econ_calendar_stale": len(instruments["econ_events"]) < 2,
        "fomc_calendar_stale": fomc.get("days_until") is None,
        "conflicts":        conflicts,
        "override_reasons": override_reasons,
        "pillars": {
            k: {"score": v["score"],
                "weight": int(PILLAR_WEIGHTS[k] * 100),
                "details": v["details"],
                "reasons": v["reasons"]}
            for k, v in pillars.items()
        },
        "ticker":            _build_ticker(quotes, instruments["btc_q"]),
        "futures_tape":      instruments["futures_tape"],
        "fear_greed_stock":  instruments["fng_stock"],
        "fear_greed_crypto": instruments["fng_crypto"],
        "spy_streak":        spy_streak,
        "vol_target":        vol_target_exposure(spy_closes_spliced),
        "timestamp":         mstate["et_time"],
        "data_sources": {
            "vix": "CBOE",
            "tnx": "US Treasury",
            "spy": _src_label(quotes.get("SPY")),
            "btc": _src_label(instruments["btc_q"]),
        },
        "data_coverage": {"requested": requested, "fetched": fetched, "failed": failed},
        "data_quality":  data_quality,
        "decision_bands": DECISION_BANDS,
    }
