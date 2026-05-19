"""
data.py — Market data fetchers with fallbacks.

Sources (in order of preference per symbol):
  ^VIX:              CBOE official CSV            →  Yahoo  →  Stooq
  ^TNX:              US Treasury official CSV      →  Yahoo  →  Stooq
  Equity/ETF/Index:  Yahoo Finance v8              →  Stooq CSV
  Bitcoin:           Yahoo Finance  →  CoinGecko   →  Binance public

^VIX and ^TNX history comes from their canonical publishers (CBOE and
US Treasury). Quotes remain Yahoo → Stooq for intraday freshness.
No API key required for any source. Thread-safe cache.
"""

from __future__ import annotations
import csv, io, json, logging, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Maximum seconds to wait for all parallel fetch futures before giving up.
_PARALLEL_TIMEOUT = 30

# ─── cache ────────────────────────────────────────────────────────────────
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_LOCK = threading.Lock()
_UA = "Mozilla/5.0 (compatible; ShouldITrade/5.0)"


def fetch_url(url: str, timeout: int = 15, cache_secs: int = 30,
              headers: dict | None = None) -> str:
    """GET a URL with a thread-safe in-memory cache."""
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(url)
        if hit and now - hit[0] < cache_secs:
            return hit[1]

    req = Request(url, headers=headers or {})
    req.add_header("User-Agent", _UA)
    req.add_header("Accept", "application/json, text/csv, */*")
    with urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")

    with _CACHE_LOCK:
        _CACHE[url] = (now, body)
    return body


# ─── yahoo finance ─────────────────────────────────────────────────────────
def _yf_sym(symbol: str) -> str:
    if symbol == "VIX":
        return "%5EVIX"
    return symbol.replace("^", "%5E")


def yf_quote(symbol: str) -> dict | None:
    """Fetch latest quote from Yahoo v8 chart. Returns None on failure."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{_yf_sym(symbol)}"
           f"?interval=1d&range=1d&includePrePost=false")
    try:
        data = json.loads(fetch_url(url, cache_secs=60))
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        if price is None or prev is None:
            return None
        change = price - prev
        return {
            "price":     round(price, 4),
            "prevClose": round(prev, 4),
            "change1d":  round(change, 4),
            "changePct": round(change / prev * 100, 4) if prev else 0.0,
            "source":    "yahoo",
        }
    except Exception:
        return None


def yf_history(symbol: str, days: int = 220) -> list[float]:
    """Fetch daily closes from Yahoo. Returns [] on failure."""
    period = "1y" if days <= 252 else "2y"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{_yf_sym(symbol)}"
           f"?interval=1d&range={period}&includePrePost=false")
    try:
        data = json.loads(fetch_url(url, cache_secs=300))
        closes = data["chart"]["result"][0]["indicators"]["quote"][0].get("close", [])
        return [c for c in closes if c is not None]
    except Exception:
        return []


def yf_ohlcv(symbol: str, days: int = 220) -> dict:
    """Fetch daily OHLCV from Yahoo (same URL as yf_history — cache hit).
    Returns {closes, volumes, highs, lows} as aligned lists, empty on failure."""
    period = "1y" if days <= 252 else "2y"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{_yf_sym(symbol)}"
           f"?interval=1d&range={period}&includePrePost=false")
    empty = {"closes": [], "volumes": [], "highs": [], "lows": []}
    try:
        q = json.loads(fetch_url(url, cache_secs=300))["chart"]["result"][0]["indicators"]["quote"][0]
        rows = [
            (c, v, h, l)
            for c, v, h, l in zip(
                q.get("close",  []), q.get("volume", []),
                q.get("high",   []), q.get("low",    []))
            if all(x is not None for x in (c, v, h, l))
        ]
        if not rows:
            return empty
        closes, volumes, highs, lows = zip(*rows)
        return {"closes": list(closes), "volumes": list(volumes),
                "highs":  list(highs),  "lows":    list(lows)}
    except Exception:
        return empty


def get_ohlcv(symbol: str, days: int = 220) -> dict:
    """OHLCV with closes-only fallback if high/low/volume are unavailable."""
    d = yf_ohlcv(symbol, days)
    if d["closes"]:
        return d
    closes = get_history(symbol, days)
    return {"closes": closes, "volumes": [], "highs": [], "lows": []}


# ─── stooq fallback ────────────────────────────────────────────────────────
# Stooq uses lowercase tickers with .us suffix for US listings and ^prefix
# for indices. Free, no key, reliable. CSV format.
_STOOQ_MAP = {
    "^VIX": "^vix", "^VIX3M": "^vix3m", "^TNX": "^tnx", "DX-Y.NYB": "^dxy",
}


def _stooq_sym(symbol: str) -> str:
    if symbol in _STOOQ_MAP:
        return _STOOQ_MAP[symbol]
    if symbol.startswith("^"):
        return symbol.lower()
    return f"{symbol.lower()}.us"


def stooq_history(symbol: str) -> list[float]:
    """Fetch daily closes from Stooq CSV."""
    url = f"https://stooq.com/q/d/l/?s={_stooq_sym(symbol)}&i=d"
    try:
        body = fetch_url(url, cache_secs=600)
        reader = csv.DictReader(io.StringIO(body))
        closes = []
        for row in reader:
            c = row.get("Close")
            if c and c not in ("N/A", "-"):
                try:
                    closes.append(float(c))
                except ValueError:
                    pass
        return closes
    except Exception:
        return []


def stooq_quote(symbol: str) -> dict | None:
    """Build a quote from Stooq daily history (last two closes)."""
    closes = stooq_history(symbol)
    if len(closes) < 2:
        return None
    price, prev = closes[-1], closes[-2]
    return {
        "price":     round(price, 4),
        "prevClose": round(prev, 4),
        "change1d":  round(price - prev, 4),
        "changePct": round((price - prev) / prev * 100, 4) if prev else 0.0,
        "source":    "stooq",
    }


# ─── Official primary sources (CBOE + US Treasury) ─────────────────────────
# Both are canonical publishers of the data, free, no API key, no UA blocking.
# Used for history only — quotes stay Yahoo→Stooq for intraday freshness.

def cboe_vix_history(limit: int = 300) -> list[float]:
    """CBOE official VIX daily closes (oldest-first). Returns [] on failure."""
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    try:
        body = fetch_url(url, cache_secs=3600)
        reader = csv.DictReader(io.StringIO(body))
        closes = []
        for row in reader:
            v = row.get("CLOSE", "").strip()
            if v:
                try:
                    closes.append(float(v))
                except ValueError:
                    pass
        return closes[-limit:] if closes else []
    except Exception:
        return []


def treasury_10y_history(limit: int = 300) -> list[float]:
    """US Treasury 10-Year yield daily (current + prior year). Returns [] on failure.
    Treasury CSV is newest-first; this reverses each batch before combining."""
    year = datetime.utcnow().year
    all_closes: list[float] = []
    for y in (year - 1, year):
        url = (
            f"https://home.treasury.gov/resource-center/data-chart-center/"
            f"interest-rates/daily-treasury-rates.csv/{y}/all"
            f"?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"
        )
        try:
            body = fetch_url(url, cache_secs=3600)
            reader = csv.DictReader(io.StringIO(body))
            batch = []
            for row in reader:
                v = row.get("10 Yr", "").strip()
                if v:
                    try:
                        batch.append(float(v))
                    except ValueError:
                        pass
            all_closes.extend(reversed(batch))  # newest-first → oldest-first
        except Exception:
            pass
    return all_closes[-limit:] if all_closes else []


_OFFICIAL_SOURCES: dict[str, callable] = {
    "^VIX": cboe_vix_history,
    "^TNX": treasury_10y_history,
}


# ─── unified getters (with fallback) ────────────────────────────────────────
def get_quote(symbol: str) -> dict | None:
    q = yf_quote(symbol)
    if q and q.get("price") is not None:
        return q
    return stooq_quote(symbol)


def get_history(symbol: str, days: int = 220) -> list[float]:
    # Use canonical publishers for VIX and 10Y yield — more reliable than Yahoo.
    # Falls back to Yahoo then Stooq if the official source fails.
    if symbol in _OFFICIAL_SOURCES:
        h = _OFFICIAL_SOURCES[symbol](limit=max(days + 80, 300))
        if len(h) >= 20:
            return h
    h = yf_history(symbol, days)
    if len(h) >= 20:
        return h
    return stooq_history(symbol) or h


# ─── equity index futures tape ─────────────────────────────────────────────
FUTURES_CONTRACTS = [
    {"symbol": "ES=F",  "label": "ES",  "name": "S&P 500",   "weight": 0.38},
    {"symbol": "NQ=F",  "label": "NQ",  "name": "Nasdaq 100", "weight": 0.34},
    {"symbol": "RTY=F", "label": "RTY", "name": "Russell",   "weight": 0.16},
    {"symbol": "YM=F",  "label": "YM",  "name": "Dow",       "weight": 0.12},
]


def _futures_item(contract: dict, q: dict | None) -> dict:
    return {
        "symbol": contract["label"],
        "name": contract["name"],
        "price": round(q.get("price"), 2) if q and q.get("price") is not None else None,
        "change_pct": round(q.get("changePct"), 2) if q and q.get("changePct") is not None else None,
        "source": q.get("source") if q else None,
        "available": bool(q and q.get("price") is not None and q.get("changePct") is not None),
    }


def fetch_futures_tape() -> dict:
    """Near-live equity-index futures context. Informational only; not scored."""
    quotes = fetch_quotes_parallel([c["symbol"] for c in FUTURES_CONTRACTS], max_workers=4)
    items = [_futures_item(c, quotes.get(c["symbol"])) for c in FUTURES_CONTRACTS]
    valid = [item for item in items if item["available"]]
    valid_labels = {item["symbol"] for item in valid}

    if len(valid) < 2:
        return {
            "valid": False,
            "tone": "Unavailable",
            "tone_color": "gray",
            "read": "Futures tape unavailable. Use cash-market breadth and daily trend context.",
            "items": items,
            "source": "Yahoo futures",
            "context_only": True,
        }

    weighted = 0.0
    weights = 0.0
    for contract, item in zip(FUTURES_CONTRACTS, items):
        if item["available"]:
            weighted += item["change_pct"] * contract["weight"]
            weights += contract["weight"]
    avg = weighted / weights if weights else 0.0

    up = sum(1 for item in valid if item["change_pct"] > 0.10)
    down = sum(1 for item in valid if item["change_pct"] < -0.10)
    es = next((i for i in items if i["symbol"] == "ES"), {})
    nq = next((i for i in items if i["symbol"] == "NQ"), {})
    rty = next((i for i in items if i["symbol"] == "RTY"), {})

    if avg >= 0.65 and up >= 3:
        tone, color = "Risk-On", "green"
    elif avg >= 0.20:
        tone, color = "Mild Risk-On", "green"
    elif avg <= -0.65 and down >= 3:
        tone, color = "Risk-Off", "red"
    elif avg <= -0.20:
        tone, color = "Mild Risk-Off", "orange"
    else:
        tone, color = "Mixed", "yellow"

    flags: list[str] = []
    if {"ES", "NQ"} <= valid_labels and es.get("change_pct", 0) > 0.15 and nq.get("change_pct", 0) > 0.15:
        if rty.get("available") and rty.get("change_pct", 0) < -0.10:
            flags.append("Mega-cap bid, small caps lagging")
    if any(abs(item["change_pct"]) >= 1.0 for item in valid):
        flags.append("Gap risk elevated")

    if tone in {"Risk-On", "Mild Risk-On"}:
        read = "Futures lean positive. Still wait for cash breadth before chasing the open."
    elif tone in {"Risk-Off", "Mild Risk-Off"}:
        read = "Futures lean defensive. Be patient with longs until the cash session confirms buyers."
    else:
        read = "Futures are mixed. Let the first cash-market range and breadth confirm direction."
    if flags:
        read = f"{read} {'; '.join(flags)}."

    return {
        "valid": True,
        "tone": tone,
        "tone_color": color,
        "weighted_change_pct": round(avg, 2),
        "read": read,
        "items": items,
        "source": "Yahoo futures",
        "context_only": True,
    }


# ─── bitcoin (special cascade) ──────────────────────────────────────────────
def btc_quote() -> dict | None:
    # 1. Yahoo
    q = yf_quote("BTC-USD")
    if q:
        return q
    # 2. CoinGecko
    try:
        body = fetch_url(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
            cache_secs=60)
        d = json.loads(body)["bitcoin"]
        return {"price": round(d["usd"], 2),
                "changePct": round(d.get("usd_24h_change", 0), 2),
                "source": "coingecko"}
    except Exception:
        pass
    # 3. Binance
    try:
        body = fetch_url(
            "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
            cache_secs=60)
        d = json.loads(body)
        return {"price": round(float(d["lastPrice"]), 2),
                "changePct": round(float(d["priceChangePercent"]), 2),
                "source": "binance"}
    except Exception:
        return None


def btc_history() -> list[float]:
    h = yf_history("BTC-USD", 220)
    if len(h) >= 20:
        return h
    # Binance klines fallback
    try:
        body = fetch_url(
            "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=220",
            cache_secs=600)
        return [float(k[4]) for k in json.loads(body)]
    except Exception:
        return []


# ─── fear & greed indexes ──────────────────────────────────────────────────
def _fng_rating(score: float) -> str:
    if score <= 25:  return "Extreme Fear"
    if score <= 45:  return "Fear"
    if score <= 55:  return "Neutral"
    if score <= 75:  return "Greed"
    return "Extreme Greed"


def fetch_fear_greed_stock() -> dict:
    """CNN Fear & Greed Index — US stock market sentiment (7 equity indicators)."""
    try:
        body = fetch_url(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/",
            cache_secs=300,
            headers={"Referer": "https://edition.cnn.com/markets/fear-and-greed"})
        d = json.loads(body)
        fg = d.get("fear_and_greed") or {}
        score = fg.get("score")
        if score is not None:
            score = float(score)
            return {
                "score":      round(score, 1),
                "rating":     str(fg.get("rating") or _fng_rating(score)),
                "prev_close": round(float(fg.get("previous_close") or score), 1),
                "prev_week":  round(float(fg.get("previous_1_week") or score), 1),
                "prev_month": round(float(fg.get("previous_1_month") or score), 1),
                "source":     "CNN",
                "available":  True,
            }
    except Exception:
        pass
    return {"available": False}


def fetch_fear_greed_crypto() -> dict:
    """alternative.me Crypto Fear & Greed Index — Bitcoin/crypto market sentiment."""
    try:
        body = fetch_url(
            "https://api.alternative.me/fng/?limit=7&format=json",
            cache_secs=300)
        entries = json.loads(body).get("data") or []
        if entries:
            cur   = entries[0]
            score = float(cur["value"])
            p1    = float(entries[1]["value"]) if len(entries) > 1 else score
            p7    = float(entries[6]["value"]) if len(entries) > 6 else score
            return {
                "score":      score,
                "rating":     cur.get("value_classification") or _fng_rating(score),
                "prev_close": p1,
                "prev_week":  p7,
                "prev_month": score,
                "source":     "alternative.me",
                "available":  True,
            }
    except Exception:
        pass
    return {"available": False}


# ─── parallel fetch helpers ─────────────────────────────────────────────────
def fetch_quotes_parallel(symbols: list[str], max_workers: int = 8) -> dict[str, dict | None]:
    """Fetch many quotes concurrently. Returns {symbol: quote_dict_or_None}."""
    out: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(get_quote, s): s for s in symbols}
        try:
            for f in as_completed(futs, timeout=_PARALLEL_TIMEOUT):
                sym = futs[f]
                try:
                    out[sym] = f.result()
                except Exception:
                    logger.debug("Quote fetch failed for %s", sym, exc_info=True)
                    out[sym] = None
        except FutureTimeoutError:
            logger.warning("fetch_quotes_parallel timed out after %ds; %d/%d symbols fetched.",
                           _PARALLEL_TIMEOUT, len(out), len(symbols))
            for sym in set(symbols) - set(out):
                out[sym] = None
    return out


def fetch_histories_parallel(pairs: list[tuple[str, int]],
                             max_workers: int = 4) -> dict[str, list[float]]:
    """Fetch many histories concurrently. pairs=[(symbol, days), ...]."""
    out: dict[str, list[float]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(get_history, s, d): s for s, d in pairs}
        try:
            for f in as_completed(futs, timeout=_PARALLEL_TIMEOUT):
                sym = futs[f]
                try:
                    out[sym] = f.result()
                except Exception:
                    logger.debug("History fetch failed for %s", sym, exc_info=True)
                    out[sym] = []
        except FutureTimeoutError:
            logger.warning("fetch_histories_parallel timed out after %ds; %d/%d symbols fetched.",
                           _PARALLEL_TIMEOUT, len(out), len(pairs))
            for _, sym in ((s, s) for s, _ in pairs):
                out.setdefault(sym, [])
    return out


# ─── market state (NYSE hours, US/Eastern) ─────────────────────────────────
# Simple approximation. ET = UTC-5 (EST) or UTC-4 (EDT). We use a rough
# DST window: 2nd Sunday of March to 1st Sunday of November. Good enough
# for open/closed labels; the dashboard does not trade off this.
def _is_dst_et(d: datetime) -> bool:
    y = d.year
    # 2nd Sunday of March
    mar1 = datetime(y, 3, 1)
    dst_start = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    # 1st Sunday of November
    nov1 = datetime(y, 11, 1)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    return dst_start <= d < dst_end


def market_state() -> dict:
    """Return current NYSE trading state + local ET time string."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    offset = -4 if _is_dst_et(now_utc) else -5
    et = now_utc + timedelta(hours=offset)
    hour, minute = et.hour, et.minute
    minutes = hour * 60 + minute

    if et.weekday() >= 5:
        state, label, color = "weekend", "Weekend", "gray"
    elif minutes < 4 * 60:                           # before 4:00 AM
        state, label, color = "closed",    "Closed",      "gray"
    elif minutes < 9 * 60 + 30:                      # 4:00 – 9:30 AM
        state, label, color = "premarket", "Pre-Market",  "orange"
    elif minutes < 16 * 60:                          # 9:30 AM – 4:00 PM
        state, label, color = "open",      "Market Open", "green"
    elif minutes < 20 * 60:                          # 4:00 – 8:00 PM
        state, label, color = "afterhours","After Hours", "orange"
    else:
        state, label, color = "closed",    "Closed",      "gray"

    return {
        "state": state, "label": label, "color": color,
        "et_time": et.strftime("%H:%M ET"),
        "et_date": et.strftime("%a %b %d"),
    }


# ─── Economic calendar ──────────────────────────────────────────────────────
# Key US economic release dates: CPI, PPI, NFP (Jobs), GDP (advance estimate).
# Source: BLS / BEA / Fed schedule.  Update this list annually.
_ECON_CALENDAR = [
    # (date, type, short_name)
    # --- 2025 ---
    ("2025-07-03", "NFP",  "Jobs Report"),
    ("2025-07-10", "CPI",  "CPI"),
    ("2025-07-11", "PPI",  "PPI"),
    ("2025-07-30", "GDP",  "GDP (Adv)"),
    ("2025-08-01", "NFP",  "Jobs Report"),
    ("2025-08-12", "CPI",  "CPI"),
    ("2025-08-13", "PPI",  "PPI"),
    ("2025-09-05", "NFP",  "Jobs Report"),
    ("2025-09-10", "CPI",  "CPI"),
    ("2025-09-11", "PPI",  "PPI"),
    ("2025-09-25", "GDP",  "GDP (Rev)"),
    ("2025-10-03", "NFP",  "Jobs Report"),
    ("2025-10-15", "CPI",  "CPI"),
    ("2025-10-14", "PPI",  "PPI"),
    ("2025-10-30", "GDP",  "GDP (Adv)"),
    ("2025-11-07", "NFP",  "Jobs Report"),
    ("2025-11-12", "CPI",  "CPI"),
    ("2025-11-13", "PPI",  "PPI"),
    ("2025-12-05", "NFP",  "Jobs Report"),
    ("2025-12-10", "CPI",  "CPI"),
    ("2025-12-11", "PPI",  "PPI"),
    ("2025-12-18", "GDP",  "GDP (Rev)"),
    # --- 2026 ---
    ("2026-01-09", "NFP",  "Jobs Report"),
    ("2026-01-14", "PPI",  "PPI"),
    ("2026-01-15", "CPI",  "CPI"),
    ("2026-01-29", "GDP",  "GDP (Adv)"),
    ("2026-02-06", "NFP",  "Jobs Report"),
    ("2026-02-11", "CPI",  "CPI"),
    ("2026-02-12", "PPI",  "PPI"),
    ("2026-03-06", "NFP",  "Jobs Report"),
    ("2026-03-11", "CPI",  "CPI"),
    ("2026-03-12", "PPI",  "PPI"),
    ("2026-03-26", "GDP",  "GDP (Rev)"),
    ("2026-04-03", "NFP",  "Jobs Report"),
    ("2026-04-10", "CPI",  "CPI"),
    ("2026-04-09", "PPI",  "PPI"),
    ("2026-04-29", "GDP",  "GDP (Adv)"),
    ("2026-05-01", "NFP",  "Jobs Report"),
    ("2026-05-12", "CPI",  "CPI"),
    ("2026-05-13", "PPI",  "PPI"),
    ("2026-06-05", "NFP",  "Jobs Report"),
    ("2026-06-10", "CPI",  "CPI"),
    ("2026-06-11", "PPI",  "PPI"),
    ("2026-06-25", "GDP",  "GDP (Rev)"),
]


def econ_proximity() -> list[dict]:
    """Return the next 3 upcoming economic releases with days-until and risk color."""
    today = datetime.utcnow().date()
    upcoming = []
    for date_str, etype, name in _ECON_CALENDAR:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        if d >= today:
            days = (d - today).days
            if days == 0:
                color, urgency = "red", "TODAY"
            elif days == 1:
                color, urgency = "red", "Tomorrow"
            elif days <= 3:
                color, urgency = "orange", f"{days}d"
            elif days <= 7:
                color, urgency = "yellow", f"{days}d"
            else:
                color, urgency = "gray", f"{days}d"
            upcoming.append({
                "date": date_str,
                "date_pretty": d.strftime("%b %d"),
                "days_until": days,
                "type": etype,
                "name": name,
                "color": color,
                "urgency": urgency,
            })
    return sorted(upcoming, key=lambda x: x["days_until"])[:3]


# ─── Options Expiration calendar ──────────────────────────────────────────────
# Standard monthly OpEx = 3rd Friday of each month.
# Quarterly (Mar/Jun/Sep/Dec) = "Triple Witching" — stock futures + index options
# + equity options all expire simultaneously. Higher gamma, pinning, and vol effects.
_QUARTERLY_OPEX_MONTHS = {3, 6, 9, 12}


def _third_friday(year: int, month: int):
    """Return the date of the 3rd Friday of the given year/month."""
    d = datetime(year, month, 1).date()
    days_to_friday = (4 - d.weekday()) % 7   # Friday = weekday 4
    return d + timedelta(days=days_to_friday + 14)  # first Friday + 2 weeks


def opex_proximity() -> dict:
    """Days until next options expiration (3rd Friday). Flags Triple Witching months."""
    today = datetime.utcnow().date()
    y, m = today.year, today.month
    # Scan the next 6 months to find the next OpEx >= today
    for _ in range(6):
        opex_date = _third_friday(y, m)
        if opex_date >= today:
            break
        m += 1
        if m > 12:
            m, y = 1, y + 1
    else:
        return {"days_until": None, "label": "N/A", "color": "gray",
                "is_quarterly": False, "kind": "OpEx", "date_pretty": None}

    is_quarterly = m in _QUARTERLY_OPEX_MONTHS
    kind = "Triple Witching" if is_quarterly else "Monthly OpEx"
    days = (opex_date - today).days

    if   days == 0: label, color = f"{kind} TODAY",       "red"
    elif days == 1: label, color = f"{kind} Tomorrow",    "red"
    elif days <= 3: label, color = f"{kind} in {days}d",  "orange"
    elif days <= 7: label, color = f"OpEx week ({days}d)", "yellow"
    else:           label, color = f"OpEx in {days}d",    "gray"

    return {
        "days_until":   days,
        "date_pretty":  opex_date.strftime("%b %d"),
        "label":        label,
        "color":        color,
        "is_quarterly": is_quarterly,
        "kind":         kind,
    }


# ─── Seasonality ────────────────────────────────────────────────────────────────
# Historical monthly S&P 500 average bias (Stock Trader's Almanac / academic data).
# Score adjustments intentionally small (max ±8 pts) — seasonality is a weak signal.
_MONTHLY_SEASONALITY = {
    1:  {"score": +3, "label": "Jan Effect",      "bias": "Mild Bullish",    "color": "green"},
    2:  {"score":  0, "label": "Feb Neutral",     "bias": "Neutral",         "color": "yellow"},
    3:  {"score": +3, "label": "Spring Rally",    "bias": "Mild Bullish",    "color": "green"},
    4:  {"score": +6, "label": "April Strength",  "bias": "Historically Strong", "color": "green"},
    5:  {"score": -5, "label": "Sell in May",     "bias": "Historically Weak","color": "orange"},
    6:  {"score":  0, "label": "June Neutral",    "bias": "Neutral",         "color": "yellow"},
    7:  {"score": +5, "label": "Summer Rally",    "bias": "Mild Bullish",    "color": "green"},
    8:  {"score": -5, "label": "Aug Weakness",    "bias": "Historically Weak","color": "orange"},
    9:  {"score": -8, "label": "September Effect","bias": "Weakest Month",   "color": "red"},
    10: {"score": +2, "label": "Oct Reversal",    "bias": "Volatile",        "color": "yellow"},
    11: {"score": +7, "label": "Year-End Rally",  "bias": "Historically Strong", "color": "green"},
    12: {"score": +6, "label": "Santa Rally",     "bias": "Historically Strong", "color": "green"},
}


def seasonality() -> dict:
    """Current month's historical seasonal bias for US equities."""
    month = datetime.utcnow().month
    s = _MONTHLY_SEASONALITY[month]
    return {
        "month":     month,
        "score_adj": s["score"],
        "label":     s["label"],
        "bias":      s["bias"],
        "color":     s["color"],
    }


# ─── Earnings Season ────────────────────────────────────────────────────────────
# Approximate windows when the bulk of S&P 500 companies report each quarter.
# Q4 → Jan/Feb, Q1 → Apr/May, Q2 → Jul/Aug, Q3 → Oct/Nov.
_EARNINGS_WINDOWS = [
    (1,  8, 2,  7,  "Q4"),
    (4,  7, 5,  2,  "Q1"),
    (7,  7, 8,  1,  "Q2"),
    (10, 7, 11, 1,  "Q3"),
]


def earnings_season() -> dict:
    """Return current or next earnings season status with gap-risk context."""
    today = datetime.utcnow()
    year  = today.year

    for ms, ds, me, de, quarter in _EARNINGS_WINDOWS:
        start = datetime(year, ms, ds)
        end   = datetime(year, me, de)
        if start <= today <= end:
            days_left = (end.date() - today.date()).days
            return {
                "in_season":  True,
                "quarter":    quarter,
                "label":      f"{quarter} Earnings",
                "detail":     f"~{days_left}d remaining",
                "color":      "orange",
                "days_until": 0,
            }

    # Not currently in a season — find the next one
    candidates = []
    for yr in (year, year + 1):
        for ms, ds, me, de, quarter in _EARNINGS_WINDOWS:
            start = datetime(yr, ms, ds)
            if start.date() > today.date():
                candidates.append(((start.date() - today.date()).days, quarter))
    if candidates:
        days_until, quarter = min(candidates)
        return {
            "in_season":  False,
            "quarter":    quarter,
            "label":      f"{quarter} Earnings",
            "detail":     f"in {days_until}d",
            "color":      "yellow" if days_until <= 14 else "gray",
            "days_until": days_until,
        }
    return {"in_season": False, "label": "N/A", "color": "gray", "days_until": None}


# 2026 FOMC meeting decision dates (day 2 of each meeting, when statement hits).
# Source: federalreserve.gov  ·  Update annually when Fed publishes new schedule.
_FOMC_2026_2027 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27",
]


def fomc_proximity() -> dict:
    """Days until next FOMC decision + event-risk label."""
    today = datetime.utcnow().date()
    upcoming = [datetime.strptime(d, "%Y-%m-%d").date() for d in _FOMC_2026_2027]
    next_date = next((d for d in upcoming if d >= today), None)
    if not next_date:
        return {"days_until": None, "date": None,
                "label": "⚠ Calendar outdated", "color": "orange"}

    days = (next_date - today).days
    if days == 0:
        label, color = "FOMC TODAY", "red"
    elif days == 1:
        label, color = "FOMC Tomorrow", "red"
    elif days <= 3:
        label, color = f"{days}d to FOMC", "red"
    elif days <= 7:
        label, color = f"{days}d to FOMC", "orange"
    elif days <= 14:
        label, color = f"{days}d to FOMC", "yellow"
    else:
        label, color = f"{days}d to FOMC", "green"

    return {
        "days_until": days,
        "date": next_date.isoformat(),
        "date_pretty": next_date.strftime("%b %d"),
        "label": label,
        "color": color,
    }
