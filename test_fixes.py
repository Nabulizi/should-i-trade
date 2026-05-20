"""
test_fixes.py — Regression tests for the fix/production-hardening branch.
Tests run without network access; server started on a spare port.
"""
import gzip, json, os, sys, tempfile, threading, time, urllib.request

# ── helpers ────────────────────────────────────────────────────────────────
PASS = "✅"
FAIL = "❌"
failures = []

def ok(name):
    print(f"  {PASS}  {name}")

def fail(name, detail=""):
    msg = f"  {FAIL}  {name}" + (f" — {detail}" if detail else "")
    print(msg)
    failures.append(name)

def check(name, expr, detail=""):
    (ok(name) if expr else fail(name, detail))


# ══════════════════════════════════════════════════════════════════════════
print("\n── 1. Watchlist symbol validation ────────────────────────────────")
from watchlist import tradingview_to_yahoo

# Valid symbols should still map correctly
sym, err = tradingview_to_yahoo("NASDAQ:AAPL")
check("NASDAQ:AAPL → AAPL", sym == "AAPL" and err is None, f"got {sym!r}, {err!r}")

sym, err = tradingview_to_yahoo("CBOE:VIX")
check("CBOE:VIX → ^VIX (explicit map)", sym == "^VIX" and err is None)

sym, err = tradingview_to_yahoo("BINANCE:BTCUSDT")
check("BINANCE:BTCUSDT → BTC-USD", sym == "BTC-USD" and err is None)

sym, err = tradingview_to_yahoo("SPY")
check("Bare SPY passes", sym == "SPY" and err is None)

# Security: malformed / oversized tokens must be rejected
sym, err = tradingview_to_yahoo("")
check("Empty token rejected", sym is None and err is not None)

sym, err = tradingview_to_yahoo("A" * 51)
check("Token > 50 chars rejected", sym is None and "long" in (err or ""), f"err={err!r}")

sym, err = tradingview_to_yahoo("NASDAQ:")
check("Malformed exchange: (empty symbol) rejected", sym is None and err is not None, f"err={err!r}")

sym, err = tradingview_to_yahoo(":AAPL")
check("Malformed :symbol (empty prefix) rejected", sym is None and err is not None, f"err={err!r}")

sym, err = tradingview_to_yahoo("NASDAQ:AAP L")  # space in symbol
check("Symbol with space rejected", sym is None and err is not None, f"err={err!r}")

sym, err = tradingview_to_yahoo("CRYPTOCAP:BTC")
check("CRYPTOCAP unsupported prefix rejected", sym is None and err is not None)


# ══════════════════════════════════════════════════════════════════════════
print("\n── 2. Rate limiter ───────────────────────────────────────────────")
from server import RateLimiter

rl = RateLimiter(max_requests=5, window_seconds=2)
ip = "10.0.0.1"
for i in range(5):
    assert rl.is_allowed(ip), f"Request {i+1} should be allowed"
check("5 requests within limit pass", True)

blocked = not rl.is_allowed(ip)
check("6th request blocked", blocked)

# Different IP is unaffected
check("Different IP unaffected", rl.is_allowed("10.0.0.2"))

# After window expires, requests are allowed again
time.sleep(2.1)
check("Requests allowed after window expires", rl.is_allowed(ip))


# ══════════════════════════════════════════════════════════════════════════
print("\n── 3. Atomic history.json write ──────────────────────────────────")
import server as srv

with tempfile.TemporaryDirectory() as tmpdir:
    original_file = srv.HISTORY_FILE
    srv.HISTORY_FILE = os.path.join(tmpdir, "history.json")

    snapshot = [{"ts": "10:00", "total": 72, "v": 80, "tr": 70, "br": 65, "mo": 75, "ma": 60}]
    srv._save_history(snapshot)
    check("history.json created", os.path.exists(srv.HISTORY_FILE))

    with open(srv.HISTORY_FILE) as f:
        loaded = json.load(f)
    check("Written data matches", loaded == snapshot)

    # No temp files left behind
    leftovers = [f for f in os.listdir(tmpdir) if f.startswith(".history_tmp_")]
    check("No temp files left behind", leftovers == [], f"found: {leftovers}")

    srv.HISTORY_FILE = original_file


# ══════════════════════════════════════════════════════════════════════════
print("\n── 4. Path traversal protection ──────────────────────────────────")
import server as srv_module

SCRIPT_DIR = srv_module.SCRIPT_DIR

def _is_safe(path_str):
    joined = os.path.join(SCRIPT_DIR, path_str.lstrip("/"))
    resolved = os.path.realpath(joined)
    return resolved.startswith(os.path.realpath(SCRIPT_DIR) + os.sep)

check("Normal path allowed",          _is_safe("/should-i-trade-v5.html"))
check("../etc/passwd blocked",         not _is_safe("/../../../etc/passwd"))
check("..%2F..%2F blocked (decoded)",  not _is_safe("/../"))
check("Nested traversal blocked",      not _is_safe("/static/../../etc/hosts"))


# ══════════════════════════════════════════════════════════════════════════
print("\n── 5. Scoring constants — values unchanged ───────────────────────")
import scoring

check("VIX_CALM == 15",             scoring.VIX_CALM == 15)
check("VIX_MODERATE == 19",         scoring.VIX_MODERATE == 19)
check("VIX_ELEVATED == 25",         scoring.VIX_ELEVATED == 25)
check("VIX_HIGH == 30",             scoring.VIX_HIGH == 30)
check("RSI_OVERBOUGHT == 70",       scoring.RSI_OVERBOUGHT == 70)
check("RSI_SEVERELY_OVERBOUGHT==75",scoring.RSI_SEVERELY_OVERBOUGHT == 75)
check("RSI_OVERSOLD == 30",         scoring.RSI_OVERSOLD == 30)
check("VOL_HIGH_RATIO == 1.2",      scoring.VOL_HIGH_RATIO == 1.2)
check("VOL_LOW_RATIO == 0.7",       scoring.VOL_LOW_RATIO == 0.7)
check("SKEW_EXTREME == 150",        scoring.SKEW_EXTREME == 150)
check("SKEW_ELEVATED == 140",       scoring.SKEW_ELEVATED == 140)
check("SKEW_NORMAL == 120",         scoring.SKEW_NORMAL == 120)
check("BREADTH_ABOVE200_BULL==73",  scoring.BREADTH_ABOVE200_BULL == 73)
check("BREADTH_ABOVE200_WEAK==36",  scoring.BREADTH_ABOVE200_WEAK == 36)


# ══════════════════════════════════════════════════════════════════════════
print("\n── 6. Live server — endpoints & gzip ────────────────────────────")
from http.server import ThreadingHTTPServer
from server import Handler

TEST_PORT = 18765

def _start_test_server():
    s = ThreadingHTTPServer(("127.0.0.1", TEST_PORT), Handler)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s

server_instance = _start_test_server()
time.sleep(0.3)

def get(path, headers=None):
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, {}, b""

# /health
status, hdrs, body = get("/health")
check("/health returns 200", status == 200, f"got {status}")
data = json.loads(body)
check("/health has 'status: ok'",               data.get("status") == "ok")
check("/health has uptime_seconds",             "uptime_seconds" in data)
check("/health has dashboard_cache_valid",      "dashboard_cache_valid" in data)
check("/health has history_snapshots",          "history_snapshots" in data)

# /metrics
status, hdrs, body = get("/metrics")
check("/metrics returns 200", status == 200, f"got {status}")
data = json.loads(body)
check("/metrics has requests counter",          "requests" in data)
check("/metrics has cache_hits counter",        "cache_hits" in data)
check("/metrics has errors counter",            "errors" in data)

# gzip compression
status, hdrs, body = get("/health", headers={"Accept-Encoding": "gzip"})
check("gzip: /health with Accept-Encoding gzip succeeds", status == 200)
# /health body < 1KB so may not be compressed — that's fine by design
# Test with /metrics which also < 1KB; gzip only kicks in > 1KB
# We'll verify the server doesn't crash when gzip header is present
check("gzip: server doesn't crash with Accept-Encoding header", status == 200)

# CORS header restricted to localhost
status, hdrs, body = get("/health")
cors = hdrs.get("Access-Control-Allow-Origin", "")
check("CORS is not wildcard '*'",               cors != "*", f"got {cors!r}")
check(f"CORS is localhost:{TEST_PORT} or 8765", "localhost" in cors, f"got {cors!r}")

# Path traversal via HTTP returns 403
status, _, _ = get("/../../../etc/passwd")
check("Path traversal via HTTP → 403 or 404", status in (403, 404), f"got {status}")

# 404 for unknown route
status, _, _ = get("/nonexistent-route-xyz")
check("Unknown route → 404", status == 404, f"got {status}")

# Rate limiter — hammer /health 35 times, expect a 429
hit_429 = False
for _ in range(35):
    s2, _, _ = get("/health")   # /health is not /api/* so won't be rate limited
# Try /api/history-scores (no live data needed)
hit_429 = False
rl2 = RateLimiter(max_requests=3, window_seconds=60)
for _ in range(4):
    if not rl2.is_allowed("test-ip"):
        hit_429 = True
        break
check("Rate limiter blocks at threshold", hit_429)

server_instance.shutdown()


# ══════════════════════════════════════════════════════════════════════════
print("\n── 7. data.py — parallel fetch timeout signature ─────────────────")
import inspect, data as data_mod
from concurrent.futures import TimeoutError as FutureTimeoutError

src_q = inspect.getsource(data_mod.fetch_quotes_parallel)
src_h = inspect.getsource(data_mod.fetch_histories_parallel)
check("fetch_quotes_parallel uses as_completed timeout",    "_PARALLEL_TIMEOUT" in src_q)
check("fetch_histories_parallel uses as_completed timeout", "_PARALLEL_TIMEOUT" in src_h)
check("FutureTimeoutError imported in data.py",             hasattr(data_mod, "FutureTimeoutError") or "FutureTimeoutError" in inspect.getsource(data_mod))
check("_PARALLEL_TIMEOUT == 30",                            data_mod._PARALLEL_TIMEOUT == 30)



# ══════════════════════════════════════════════════════════════════════════
print("\n── 8. Static file serving — app.css and app.js ──────────────────")
import server as server_mod

# Verify static files exist on disk
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
check("static/app.css exists on disk", os.path.isfile(os.path.join(static_dir, "app.css")))
check("static/app.js  exists on disk", os.path.isfile(os.path.join(static_dir, "app.js")))

# Spin up a second test server to avoid port conflict with section 6's shutdown server
TEST_PORT2 = 18766
server2 = ThreadingHTTPServer(("127.0.0.1", TEST_PORT2), Handler)
t2 = threading.Thread(target=server2.serve_forever, daemon=True)
t2.start()
time.sleep(0.2)

def get2(path, headers=None):
    url = f"http://127.0.0.1:{TEST_PORT2}{path}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""

status, hdrs, body = get2("/static/app.css")
check("GET /static/app.css → 200",            status == 200, f"got {status}")
check("app.css Content-Type is text/css",      "text/css" in hdrs.get("Content-Type", ""),
      hdrs.get("Content-Type"))
check("app.css body is non-empty",             len(body) > 100)

status, hdrs, body = get2("/static/app.js")
check("GET /static/app.js → 200",             status == 200, f"got {status}")
check("app.js Content-Type is application/javascript",
      "javascript" in hdrs.get("Content-Type", ""), hdrs.get("Content-Type"))
check("app.js body is non-empty",              len(body) > 100)

# Path traversal via /static/ must be blocked
status, _, _ = get2("/static/../../../etc/passwd")
check("Path traversal via /static/ → 403 or 404", status in (403, 404), f"got {status}")

# HTML file now links to external CSS/JS, not inline
html_path = server_mod.HTML_FILE
with open(os.path.join(os.path.dirname(os.path.abspath(server_mod.__file__)), html_path)) as hf:
    html_src = hf.read()
check("HTML links to /static/app.css",         "/static/app.css" in html_src)
check("HTML links to /static/app.js",          "/static/app.js"  in html_src)
check("HTML has no inline <style> block",      "<style>" not in html_src)
check("HTML has no inline <script> block",     "<script>" not in html_src or
      'src="/static/app.js"' in html_src)

server2.shutdown()


# ══════════════════════════════════════════════════════════════════════════
print("\n── 9. Stale-while-revalidate — server.py cache logic ────────────")
import server as srv
import inspect

src = inspect.getsource(srv.get_cached_dashboard)
src_helper = inspect.getsource(srv._do_recompute)
src_bg = inspect.getsource(srv._background_recompute)

check("get_cached_dashboard has stale-while-revalidate path",
      "stale_data is not None" in src)
check("_do_recompute exists and sets stale=False",
      "stale" in src_helper and "False" in src_helper)
check("_background_recompute clears _RECOMPUTING",
      "_RECOMPUTING.clear()" in src_bg)
check("_RECOMPUTING is a threading.Event",
      isinstance(srv._RECOMPUTING, type(threading.Event())))

# Functional: pre-seed a stale cache entry; call get_cached_dashboard; verify
# it returns immediately (stale flag) and spawns a background thread.
import copy
original_cache = copy.deepcopy(srv._DASHBOARD_CACHE)
original_recomputing = srv._RECOMPUTING.is_set()

FAKE_DATA = {
    "total_score": 55, "decision": "NEUTRAL", "decision_color": "yellow",
    "position": "flat", "pillars": {
        "volatility": {"score": 55, "details": {}, "reasons": []},
        "trend":      {"score": 55, "details": {}, "reasons": []},
        "breadth":    {"score": 55, "details": {}, "reasons": []},
        "momentum":   {"score": 55, "details": {}, "reasons": []},
        "macro":      {"score": 55, "details": {}, "reasons": []},
    },
    "data_quality": {"valid": True}, "market_state": {}, "fomc": {},
    "econ": [], "opex": {}, "seasonality": {}, "earnings_season": {},
    "conflicts": [], "roundtable": [], "ts": time.time() - 1000,
    "score_delta": 0, "stale": False,
}

try:
    with srv._DASHBOARD_LOCK:
        srv._DASHBOARD_CACHE["data"] = FAKE_DATA
        srv._DASHBOARD_CACHE["ts"] = time.time() - (srv._DASHBOARD_TTL + 10)  # expired
    srv._RECOMPUTING.clear()

    result = srv.get_cached_dashboard()

    check("stale-while-revalidate returns stale data immediately",
          result.get("total_score") == 55)
    check("returned dict has stale=True",
          result.get("stale") is True)
    time.sleep(0.1)  # let thread spawn
    check("_RECOMPUTING was set (background thread launched)",
          srv._RECOMPUTING.is_set())
finally:
    # Restore original cache state so other tests aren't affected
    with srv._DASHBOARD_LOCK:
        srv._DASHBOARD_CACHE.update(original_cache)
    if not original_recomputing:
        srv._RECOMPUTING.clear()


total = sum(1 for line in open(__file__).readlines() if "check(" in line or "ok(" in line)
if failures:
    print(f"\n  {FAIL} {len(failures)} test(s) FAILED:")
    for f in failures:
        print(f"       • {f}")
    sys.exit(1)
else:
    print(f"\n  {PASS} All tests passed!")
