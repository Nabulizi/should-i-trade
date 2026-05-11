"""
data.py — Market data fetchers with fallbacks.

Sources (in order of preference per symbol):
  Equity/ETF/Index:  Yahoo Finance v8  →  Stooq CSV
  Bitcoin:           Yahoo Finance    →  CoinGecko  →  Binance public

All functions return plain dicts or lists; no external dependencies.
Thread-safe cache. Parallel fetch helpers for dashboard use.
"""

from __future__ import annotations
import csv, io, json, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

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


# ─── unified getters (with fallback) ────────────────────────────────────────
def get_quote(symbol: str) -> dict | None:
    q = yf_quote(symbol)
    if q and q.get("price") is not None:
        return q
    return stooq_quote(symbol)


def get_history(symbol: str, days: int = 220) -> list[float]:
    h = yf_history(symbol, days)
    if len(h) >= 20:
        return h
    return stooq_history(symbol) or h


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


# ─── fear & greed index ────────────────────────────────────────────────────
def _fng_rating(score: float) -> str:
    if score <= 25:  return "Extreme Fear"
    if score <= 45:  return "Fear"
    if score <= 55:  return "Neutral"
    if score <= 75:  return "Greed"
    return "Extreme Greed"


def fetch_fear_greed() -> dict:
    """Fetch Fear & Greed Index. Primary: CNN (stock market). Fallback: alternative.me (crypto)."""
    # 1. CNN Fear & Greed Index
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

    # 2. alternative.me crypto F&G (widely tracked sentiment proxy)
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
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out


def fetch_histories_parallel(pairs: list[tuple[str, int]],
                             max_workers: int = 4) -> dict[str, list[float]]:
    """Fetch many histories concurrently. pairs=[(symbol, days), ...]."""
    out: dict[str, list[float]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(get_history, s, d): s for s, d in pairs}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
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
    ("2026-05-13", "CPI",  "CPI"),
    ("2026-05-14", "PPI",  "PPI"),
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
                "label": "Calendar outdated", "color": "gray"}

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
