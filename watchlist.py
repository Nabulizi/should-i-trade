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

EXPLICIT_SYMBOL_MAP = {
    "CBOE:VIX": "^VIX",
    "SP:SPX": "^GSPC",
    "OANDA:XAUUSD": "XAUUSD=X",
    "TVC:SILVER": "SI=F",
    "TVC:USOIL": "CL=F",
    "BITSTAMP:BTCUSD": "BTC-USD",
    "COINBASE:LINKUSD": "LINK-USD",
}


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


def _classify(symbol: str, tv_symbol: str, q: dict | None, closes: list[float]) -> dict[str, Any]:
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
        bucket, label = "a_plus", "A+ Trend"
    elif above50 and (above200 or ma200 is None) and (near_20 or near_50) and not extended:
        bucket, label = "pullback", "Pullback Watch"
    elif extended:
        bucket, label = "extended", "Do Not Chase"
    elif (ma50 and price and price < ma50) or (ma200 and price and price < ma200) or score < 45:
        bucket, label = "broken", "Broken/Avoid"
    else:
        bucket, label = "neutral", "Neutral"

    return {
        "tv_symbol": tv_symbol,
        "symbol": symbol,
        "price": round(price, 2) if price else None,
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "score": score,
        "bucket": bucket,
        "label": label,
        "rsi14": rsi,
        "ret_1m": round(ret_1m, 2) if ret_1m is not None else None,
        "ret_3m": round(ret_3m, 2) if ret_3m is not None else None,
        "from_3m_high": round(from_high, 1) if from_high is not None else None,
        "above_20": above20,
        "above_50": above50,
        "above_200": above200,
        "source": q.get("source") if q else None,
    }


def compute_watchlist_health(path: str = DEFAULT_WATCHLIST) -> dict[str, Any]:
    tokens = _tokens_from_file(path)
    mapped: list[tuple[str, str]] = []
    skipped = []
    seen = set()
    for token in tokens:
        yahoo, reason = tradingview_to_yahoo(token)
        if not yahoo:
            skipped.append({"tv_symbol": token, "reason": reason})
            continue
        key = (token, yahoo)
        if key not in seen:
            mapped.append((token, yahoo))
            seen.add(key)

    rows = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        quote_futs = {ex.submit(get_quote, sym): (tv, sym) for tv, sym in mapped}
        hist_futs = {ex.submit(get_history, sym, 220): (tv, sym) for tv, sym in mapped}
        quotes = {quote_futs[f]: f.result() for f in as_completed(quote_futs)}
        histories = {hist_futs[f]: f.result() for f in as_completed(hist_futs)}

    for tv, sym in mapped:
        rows.append(_classify(sym, tv, quotes.get((tv, sym)), histories.get((tv, sym), [])))

    rows.sort(key=lambda r: (r["score"], r.get("ret_1m") or -999), reverse=True)
    counts = {k: 0 for k in ("a_plus", "pullback", "extended", "broken", "neutral", "unavailable")}
    for row in rows:
        counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1

    weakest = sorted(rows, key=lambda r: (r["score"], r.get("ret_1m") or 999))[:5]
    return {
        "name": os.path.basename(path),
        "path": path,
        "total": len(tokens),
        "mapped": len(mapped),
        "scanned": len(rows),
        "skipped": skipped,
        "counts": counts,
        "top": rows[:5],
        "weakest": weakest,
        "candidates": [r for r in rows if r["bucket"] in ("a_plus", "pullback")][:8],
    }
