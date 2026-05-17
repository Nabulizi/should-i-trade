#!/usr/bin/env python3
"""
Should I Trade? — Market Quality Terminal v5

Run:  python3 server.py
Open: http://localhost:8765

Data: Yahoo Finance (primary) + Stooq / CoinGecko / Binance (fallbacks)
AI:   Local multi-persona trading desk roundtable (no API key)
"""

from __future__ import annotations
import json, os, threading, time, webbrowser
from collections import deque
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from scoring import compute_dashboard
from analysis import roundtable
from watchlist import compute_watchlist_health

PORT = 8765
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = "should-i-trade-v5.html"
HISTORY_FILE = os.path.join(SCRIPT_DIR, "history.json")

# In-memory score history for sparkline. Persisted to history.json on each update.
_HISTORY: deque[dict] = deque(maxlen=144)   # ~12 hours at 5-min intervals
_HISTORY_LOCK = threading.Lock()
_HISTORY_META = {"last_ts": 0.0}            # tracks last-append time; avoids using wrong variable

# Dashboard cache — avoid re-fetching on parallel tab requests
_DASHBOARD_CACHE = {"ts": 0.0, "data": None}
_DASHBOARD_TTL = 60   # seconds
_DASHBOARD_LOCK = threading.Lock()
_COMPUTE_LOCK   = threading.Lock()   # serialises computation; prevents thundering herd

_WATCHLIST_CACHE = {"ts": 0.0, "data": None, "mtime": 0.0}
_WATCHLIST_TTL = 300  # seconds
_WATCHLIST_LOCK = threading.Lock()


def _load_history() -> None:
    """Load persisted score history from disk into _HISTORY deque on startup."""
    try:
        with open(HISTORY_FILE) as f:
            saved = json.load(f)
        with _HISTORY_LOCK:
            for item in saved[-144:]:
                _HISTORY.append(item)
        print(f"  History: loaded {len(_HISTORY)} snapshot(s) from history.json")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass  # fresh start is fine


def _save_history(snapshot: list) -> None:
    """Persist a pre-copied history list to disk. Must NOT hold _HISTORY_LOCK when calling."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(snapshot, f)
    except Exception:
        pass


def get_cached_dashboard() -> dict:
    # Fast path — cache hit, no blocking
    with _DASHBOARD_LOCK:
        now = time.time()
        if _DASHBOARD_CACHE["data"] and now - _DASHBOARD_CACHE["ts"] < _DASHBOARD_TTL:
            return _DASHBOARD_CACHE["data"]

    # Cache miss — only one thread computes; the rest queue here then get the
    # fresh result from cache (double-checked locking pattern).
    with _COMPUTE_LOCK:
        with _DASHBOARD_LOCK:
            now = time.time()
            if _DASHBOARD_CACHE["data"] and now - _DASHBOARD_CACHE["ts"] < _DASHBOARD_TTL:
                return _DASHBOARD_CACHE["data"]

        data = compute_dashboard()

        # Score delta vs. last recorded snapshot (before we append the new one).
        # Invalid feed states should not display fake score collapses.
        if data.get("data_quality", {}).get("valid", True):
            with _HISTORY_LOCK:
                prev_total = _HISTORY[-1]["total"] if _HISTORY else None
            data["score_delta"] = (data["total_score"] - prev_total
                                   if prev_total is not None else None)
        else:
            data["score_delta"] = None

        with _DASHBOARD_LOCK:
            _DASHBOARD_CACHE["data"] = data
            _DASHBOARD_CACHE["ts"] = time.time()

    # Record in history only when live data is trustworthy. Missing feeds should
    # not create fake score drops that pollute the sparkline.
    if data.get("data_quality", {}).get("valid", True):
        now_ts = time.time()
        snapshot = {
            "ts": time.strftime("%H:%M", time.gmtime()),
            "total": data["total_score"],
            "v": data["pillars"]["volatility"]["score"],
            "tr": data["pillars"]["trend"]["score"],
            "br": data["pillars"]["breadth"]["score"],
            "mo": data["pillars"]["momentum"]["score"],
            "ma": data["pillars"]["macro"]["score"],
        }
        history_copy = None
        with _HISTORY_LOCK:
            # Record if score changed or >=5 min have elapsed since last entry
            if not _HISTORY or _HISTORY[-1]["total"] != snapshot["total"] \
                    or now_ts - _HISTORY_META["last_ts"] > 300:
                _HISTORY.append(snapshot)
                _HISTORY_META["last_ts"] = now_ts
                history_copy = list(_HISTORY)    # copy while lock is held
        if history_copy is not None:
            _save_history(history_copy)          # I/O outside the lock - no deadlock

    return data


def get_cached_watchlist_health() -> dict:
    from watchlist import DEFAULT_WATCHLIST
    try:
        current_mtime = os.path.getmtime(DEFAULT_WATCHLIST)
    except OSError:
        current_mtime = 0.0

    with _WATCHLIST_LOCK:
        now = time.time()
        file_unchanged = current_mtime == _WATCHLIST_CACHE["mtime"]
        if (_WATCHLIST_CACHE["data"] and file_unchanged
                and now - _WATCHLIST_CACHE["ts"] < _WATCHLIST_TTL):
            return _WATCHLIST_CACHE["data"]

    # Get regime context from dashboard cache to gate pullback signals
    spy_above_200 = True
    try:
        dash = _DASHBOARD_CACHE.get("data") or {}
        spy_above_200 = dash.get("pillars", {}).get("trend", {}).get("details", {}).get("above_200", True)
    except Exception:
        pass

    data = compute_watchlist_health(spy_above_200=spy_above_200)
    with _WATCHLIST_LOCK:
        _WATCHLIST_CACHE["data"] = data
        _WATCHLIST_CACHE["ts"] = time.time()
        _WATCHLIST_CACHE["mtime"] = current_mtime
    return data


# ─── HTTP handler ──────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        code = str(args[1]) if len(args) > 1 else "?"
        path = str(args[0])[:60]
        color = ("\033[32m" if code.startswith("2")
                 else "\033[33m" if code.startswith("3")
                 else "\033[31m")
        print(f"  {color}{code}\033[0m  {path}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype="text/html; charset=utf-8"):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ── dashboard ──────────────────────────────────────────────────────
        if path == "/api/dashboard":
            try:
                self._json(get_cached_dashboard())
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        # ── score history (sparkline) ──────────────────────────────────────
        if path == "/api/history-scores":
            with _HISTORY_LOCK:
                self._json({"history": list(_HISTORY)})
            return

        # ── roundtable analysis ────────────────────────────────────────────
        if path == "/api/analysis":
            try:
                data = get_cached_dashboard()
                self._json(roundtable(data))
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        # ── TradingView watchlist health ───────────────────────────────────
        if path == "/api/watchlist-health":
            try:
                self._json(get_cached_watchlist_health())
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        # ── html routes ────────────────────────────────────────────────────
        if path in ("/", "/index.html", "/v5", "/v5/"):
            self._file(os.path.join(SCRIPT_DIR, HTML_FILE))
            return

        # ── static files ───────────────────────────────────────────────────
        static_path = os.path.join(SCRIPT_DIR, path.lstrip("/"))
        if os.path.isfile(static_path):
            ext = path.rsplit(".", 1)[-1]
            types = {"html": "text/html", "js": "application/javascript",
                     "css": "text/css", "json": "application/json"}
            self._file(static_path, types.get(ext, "application/octet-stream"))
            return

        self._json({"error": "not found"}, 404)


def main():
    html = os.path.join(SCRIPT_DIR, HTML_FILE)
    missing = "" if os.path.exists(html) else f"  ⚠  {HTML_FILE} not found in this folder!\n"

    print("\n  ╔══════════════════════════════════════════════╗")
    print("  ║  Should I Trade?  ·  Market Quality v6       ║")
    print("  ║  5-Pillar Score + Desk Roundtable            ║")
    print("  ╚══════════════════════════════════════════════╝")
    if missing: print(f"\n{missing}")
    print(f"\n  URL:        http://localhost:{PORT}")
    print(f"  Data:       Yahoo → Stooq fallback (free, no key)")
    print(f"  AI:         Local 5-persona desk (no key)")
    print("\n  Press Ctrl+C to stop.\n")

    _load_history()

    threading.Thread(
        target=lambda: (time.sleep(1.2), webbrowser.open(f"http://localhost:{PORT}")),
        daemon=True,
    ).start()

    # ThreadingHTTPServer so a slow /api/dashboard doesn't block /api/history
    server = ThreadingHTTPServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")


if __name__ == "__main__":
    main()
