"""
watchlist.py - TradingView watchlist import + compact health scoring.

The dashboard stays a market-regime tool; this module only summarizes whether
the exported TradingView names are worth stalking in the current tape.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from data import get_quote, get_history

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_DIR = os.path.join(SCRIPT_DIR, "watchlists")
DEFAULT_WATCHLIST = os.path.join(WATCHLIST_DIR, "Watchlist_Nur.txt")

UNSUPPORTED_PREFIXES = {"CRYPTOCAP"}
TACTICAL_SYMBOLS = {"BITI", "METD", "TSLL", "TSLZ", "TQQQ", "SQQQ", "UVXY"}
MARKET_CONTEXT_SYMBOLS = {"SPY", "QQQ", "VOO", "^GSPC", "^VIX", "SGOV", "IBIT"}
THEMATIC_ETFS = {"COPX"}
DISPLAY_ASSET_TYPES = {"equity", "etf"}

EXPLICIT_SYMBOL_MAP = {
    "CBOE:VIX": "^VIX",
    "SP:SPX": "^GSPC",
    "OANDA:XAUUSD": "XAUUSD=X",
    "TVC:SILVER": "SI=F",
    "TVC:USOIL": "CL=F",
    "BITSTAMP:BTCUSD": "BTC-USD",
    "COINBASE:LINKUSD": "LINK-USD",
}


def _asset_type(tv_symbol: str, yahoo_symbol: str) -> str:
    prefix = tv_symbol.split(":", 1)[0] if ":" in tv_symbol else ""
    if prefix in {"BINANCE", "BITSTAMP", "COINBASE"} or yahoo_symbol.endswith(("-USD", "-BTC")):
        return "crypto"
    if prefix in {"OANDA", "TVC"} or yahoo_symbol in {"XAUUSD=X", "SI=F", "CL=F"}:
        return "commodity"
    if yahoo_symbol in MARKET_CONTEXT_SYMBOLS:
        return "market_context"
    if yahoo_symbol in TACTICAL_SYMBOLS:
        return "tactical"
    if yahoo_symbol in THEMATIC_ETFS:
        return "etf"
    if prefix in {"NASDAQ", "NYSE", "AMEX"}:
        return "equity"
    if prefix in {"SP", "CBOE"}:
        return "market_context"
    return "other"


def _tokens_from_file(path: str = DEFAULT_WATCHLIST) -> list[str]:
    try:
        raw = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return []
    return [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]


def tradingview_to_yahoo(token: str) -> tuple[str | None, str | None]:
    """Map a TradingView export token to a Yahoo-friendly symbol."""
    token = token.strip().upper()
    if not token:
        return None, "empty symbol"
    if token in EXPLICIT_SYMBOL_MAP:
        return EXPLICIT_SYMBOL_MAP[token], None
    if ":" not in token:
        return token, None

    prefix, symbol = token.split(":", 1)
    if prefix in UNSUPPORTED_PREFIXES:
        return None, f"{prefix} is not available from Yahoo-style feeds"

    if prefix in {"NASDAQ", "NYSE", "AMEX", "CBOE"}:
        return symbol, None

    if prefix == "BINANCE":
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}-USD", None
        if symbol.endswith("USD"):
            return f"{symbol[:-3]}-USD", None
        if symbol.endswith("BTC"):
            return f"{symbol[:-3]}-BTC", None

    return None, f"no mapper for {prefix}:{symbol}"


def _ma(closes: list[float], n: int) -> float | None:
    if len(closes) < max(5, int(n * 0.75)):
        return None
    data = closes[-n:]
    return sum(data) / len(data)


def _rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_g = gains / n
    avg_l = losses / n
    for i in range(n + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        avg_g = (avg_g * (n - 1) + max(diff, 0)) / n
        avg_l = (avg_l * (n - 1) + max(-diff, 0)) / n
    if avg_l == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_g / avg_l), 1)


def _pct_from(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback or not closes[-lookback]:
        return None
    return (closes[-1] / closes[-lookback] - 1) * 100


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.1f}%"


def _entry_state(bucket: str, ret_1m: float | None) -> tuple[str, str]:
    if bucket == "pullback":
        if ret_1m is not None and ret_1m > 0:
            return "Ready", "green"
        return "Watch", "yellow"
    if bucket == "bear_regime":
        return "No Regime", "red"
    if bucket == "a_plus":
        return "Watch", "yellow"
    if bucket == "extended":
        return "Wait", "orange"
    if bucket == "broken":
        return "Avoid", "red"
    if bucket == "unavailable":
        return "No Data", "gray"
    return "Watch", "yellow"


def _why_text(bucket: str, above20: bool, above50: bool, above200: bool,
              rsi: float | None, ret_1m: float | None,
              dist_20: float | None, dist_50: float | None) -> str:
    parts = []
    if bucket == "a_plus":
        parts.append("above 20/50/200d" if above20 and above50 and above200 else "trend stack improving")
    elif bucket == "pullback":
        near = []
        if dist_20 is not None and abs(dist_20) <= 3.5:
            near.append("20d")
        if dist_50 is not None and abs(dist_50) <= 4.0:
            near.append("50d")
        parts.append(f"near {'/'.join(near)}" if near else "pulling into support")
    elif bucket == "bear_regime":
        return "pullback in bear market — SPY below 200d, wait for regime to clear"
    elif bucket == "extended":
        parts.append(f"{_fmt_pct(dist_20)} vs 20d" if dist_20 is not None else "extended from support")
    elif bucket == "broken":
        broken = []
        if not above20:
            broken.append("20d")
        if not above50:
            broken.append("50d")
        if not above200:
            broken.append("200d")
        parts.append(f"below {'/'.join(broken)}" if broken else "weak trend score")
    elif bucket == "unavailable":
        return "quote/history unavailable"

    if ret_1m is not None:
        parts.append(f"1M {_fmt_pct(ret_1m)}")
    if rsi is not None:
        parts.append(f"RSI {rsi:.1f}")
    return " | ".join(parts)


def _classify(symbol: str, tv_symbol: str, asset_type: str,
              q: dict | None, closes: list[float]) -> dict[str, Any]:
    if asset_type not in DISPLAY_ASSET_TYPES:
        return {"tv_symbol": tv_symbol, "symbol": symbol, "asset_type": asset_type,
                "bucket": "unavailable", "label": "Not Scored", "entry_state": "N/A",
                "entry_color": "gray", "why": f"{asset_type} not scored with equity logic",
                "score": 0, "price": None, "change_pct": None}
    price = q.get("price") if q else (closes[-1] if closes else None)
    change_pct = q.get("changePct") if q else None
    clean_closes = [c for c in closes if c is not None]
    ma20 = _ma(clean_closes, 20)
    ma50 = _ma(clean_closes, 50)
    ma200 = _ma(clean_closes, 200)
    rsi = _rsi(clean_closes)
    ret_1m = _pct_from(clean_closes, 22)
    ret_3m = _pct_from(clean_closes, 64)
    high_3m = max(clean_closes[-64:]) if len(clean_closes) >= 20 else None
    from_high = (price / high_3m - 1) * 100 if price and high_3m else None

    above20 = bool(price and ma20 and price > ma20)
    above50 = bool(price and ma50 and price > ma50)
    above200 = bool(price and ma200 and price > ma200)
    dist_20 = (price / ma20 - 1) * 100 if price and ma20 else None
    dist_50 = (price / ma50 - 1) * 100 if price and ma50 else None

    score = 35
    if above20: score += 15
    if above50: score += 20
    if above200: score += 20
    if ret_1m is not None:
        score += 10 if ret_1m > 5 else 5 if ret_1m > 0 else -8
    if ret_3m is not None:
        score += 10 if ret_3m > 10 else 5 if ret_3m > 0 else -8
    if rsi is not None and rsi >= 75:
        score -= 12
    score = max(0, min(100, int(score)))

    near_20 = bool(price and ma20 and abs(price / ma20 - 1) <= 0.035)
    near_50 = bool(price and ma50 and abs(price / ma50 - 1) <= 0.04)
    extended = bool((rsi and rsi >= 72) or (price and ma20 and price > ma20 * 1.08))

    if not q or not clean_closes:
        bucket, label = "unavailable", "No Data"
    elif above20 and above50 and above200 and not extended and score >= 75:
        bucket, label = "a_plus", "Strong Trend"
    elif above50 and (above200 or ma200 is None) and (near_20 or near_50) and not extended:
        bucket, label = "pullback", "Pullback Watch"
    elif extended:
        bucket, label = "extended", "Do Not Chase"
    elif (ma50 and price and price < ma50) or (ma200 and price and price < ma200) or score < 45:
        bucket, label = "broken", "Broken/Avoid"
    else:
        bucket, label = "neutral", "Neutral"
    entry_state, entry_color = _entry_state(bucket, ret_1m)
    why = _why_text(bucket, above20, above50, above200, rsi, ret_1m, dist_20, dist_50)

    return {
        "tv_symbol": tv_symbol,
        "symbol": symbol,
        "asset_type": asset_type,
        "price": round(price, 2) if price else None,
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "score": score,
        "bucket": bucket,
        "label": label,
        "entry_state": entry_state,
        "entry_color": entry_color,
        "why": why,
        "rsi14": rsi,
        "ret_1m": round(ret_1m, 2) if ret_1m is not None else None,
        "ret_3m": round(ret_3m, 2) if ret_3m is not None else None,
        "from_3m_high": round(from_high, 1) if from_high is not None else None,
        "dist_20": round(dist_20, 1) if dist_20 is not None else None,
        "dist_50": round(dist_50, 1) if dist_50 is not None else None,
        "above_20": above20,
        "above_50": above50,
        "above_200": above200,
        "source": q.get("source") if q else None,
    }


def compute_watchlist_health(path: str = DEFAULT_WATCHLIST,
                             spy_above_200: bool = True) -> dict[str, Any]:
    tokens = _tokens_from_file(path)
    mapped: list[tuple[str, str, str]] = []
    skipped = []
    seen = set()
    for token in tokens:
        yahoo, reason = tradingview_to_yahoo(token)
        if not yahoo:
            skipped.append({"tv_symbol": token, "reason": reason})
            continue
        asset_type = _asset_type(token, yahoo)
        key = (token, yahoo)
        if key not in seen:
            mapped.append((token, yahoo, asset_type))
            seen.add(key)

    scan_targets = [item for item in mapped if item[2] in DISPLAY_ASSET_TYPES]
    rows = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        quote_futs = {ex.submit(get_quote, sym): (tv, sym, atype) for tv, sym, atype in scan_targets}
        hist_futs = {ex.submit(get_history, sym, 220): (tv, sym, atype) for tv, sym, atype in scan_targets}
        quotes = {quote_futs[f]: f.result() for f in as_completed(quote_futs)}
        histories = {hist_futs[f]: f.result() for f in as_completed(hist_futs)}

    for tv, sym, atype in scan_targets:
        key = (tv, sym, atype)
        row = _classify(sym, tv, atype, quotes.get(key), histories.get(key, []))
        # Downgrade pullbacks in bear-market regime — they're falling knives, not entries
        if row["bucket"] == "pullback" and not spy_above_200:
            row["bucket"] = "bear_regime"
            row["label"] = "Wait for Regime"
            row["entry_state"], row["entry_color"] = "No Regime", "red"
            row["why"] = _why_text("bear_regime", False, False, False, row.get("rsi14"), row.get("ret_1m"), row.get("dist_20"), row.get("dist_50"))
        rows.append(row)

    rows.sort(key=lambda r: (r["score"], r.get("ret_1m") or -999), reverse=True)
    counts = {k: 0 for k in ("a_plus", "pullback", "bear_regime", "extended", "broken", "neutral", "unavailable")}
    asset_counts: dict[str, int] = {}
    for _, _, asset_type in mapped:
        asset_counts[asset_type] = asset_counts.get(asset_type, 0) + 1
    for row in rows:
        counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1

    watch_views = {
        "a_plus":      [r for r in rows if r["bucket"] == "a_plus"],
        "pullback":    [r for r in rows if r["bucket"] == "pullback"],
        "bear_regime": [r for r in rows if r["bucket"] == "bear_regime"],
        "extended":    [r for r in rows if r["bucket"] == "extended"],
        "broken":      [r for r in rows if r["bucket"] == "broken"],
        "neutral":     [r for r in rows if r["bucket"] == "neutral"],
        "unavailable": [r for r in rows if r["bucket"] == "unavailable"],
    }
    return {
        "name": os.path.basename(path),
        "path": path,
        "total": len(tokens),
        "mapped": len(mapped),
        "scanned": len(rows),
        "tradable_scanned": len(rows),
        "ignored": len(mapped) - len(scan_targets),
        "skipped": skipped,
        "counts": counts,
        "tradable_counts": counts,
        "asset_counts": asset_counts,
        "watch_views": watch_views,
    }
