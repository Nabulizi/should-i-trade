#!/usr/bin/env python3
"""
Should I Trade? — Market Quality Terminal v5

Run:  python3 server.py
Open: http://localhost:8765

Data: Yahoo Finance (primary) + Stooq / CoinGecko / Binance (fallbacks)
AI:   Local multi-persona trading desk roundtable (no API key)
"""

from __future__ import annotations
import gzip, json, logging, os, queue, shutil, tempfile, threading, time, webbrowser
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from scoring import compute_dashboard
from analysis import roundtable
from watchlist import compute_watchlist_health
from config import (
    PORT as _CONFIG_PORT, DASHBOARD_TTL, WATCHLIST_TTL, HISTORY_MAXLEN,
    RATE_LIMIT_MAX, RATE_LIMIT_WINDOW, SSE_KEEPALIVE_SECS,
)

# Production-aware PORT: Render (and most PaaS) inject PORT as env var.
# Falls back to config.PORT for local dev.
PORT = int(os.environ.get("PORT", _CONFIG_PORT))
IS_PRODUCTION = bool(os.environ.get("PORT") or os.environ.get("RENDER"))

# ─── logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = "should-i-trade-v5.html"
HISTORY_FILE = os.path.join(SCRIPT_DIR, "history.json")
# In production, allow all origins (public dashboard, no auth).
# Locally, restrict to dev URL.
_ALLOWED_ORIGIN = "*" if IS_PRODUCTION else f"http://localhost:{PORT}"
_SERVER_START = time.time()

# In-memory score history for sparkline. Persisted to history.json on each update.
_HISTORY: deque[dict] = deque(maxlen=HISTORY_MAXLEN)
_HISTORY_LOCK = threading.Lock()
_HISTORY_META = {"last_ts": 0.0}            # tracks last-append time

# Dashboard cache — avoid re-fetching on parallel tab requests
_DASHBOARD_CACHE = {"ts": 0.0, "data": None}
_DASHBOARD_TTL = DASHBOARD_TTL
_DASHBOARD_LOCK = threading.Lock()
_COMPUTE_LOCK   = threading.Lock()   # serialises computation; prevents thundering herd
_RECOMPUTING    = threading.Event()  # set while a background stale-while-revalidate thread runs

_WATCHLIST_CACHE = {"ts": 0.0, "data": None, "mtime": 0.0}
_WATCHLIST_TTL = WATCHLIST_TTL
_WATCHLIST_LOCK = threading.Lock()

# Request counters for /metrics endpoint
_METRICS: dict[str, int] = {"requests": 0, "cache_hits": 0, "cache_misses": 0, "errors": 0}
_METRICS_LOCK = threading.Lock()

# Server-Sent Events — connected client queues
_SSE_CLIENTS: list[queue.Queue] = []
_SSE_LOCK = threading.Lock()


def _sse_broadcast(event_type: str, data: dict) -> None:
    """Push a JSON event to all connected SSE clients (non-blocking)."""
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _SSE_LOCK:
        clients = list(_SSE_CLIENTS)
    for q in clients:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass   # slow client; they'll rely on the next event


# ─── Rate Limiter ──────────────────────────────────────────────────────────
class RateLimiter:
    """Sliding-window per-IP rate limiter: max_requests per window_seconds."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            timestamps = [t for t in self._buckets.get(client_ip, []) if t > cutoff]
            if len(timestamps) >= self.max_requests:
                self._buckets[client_ip] = timestamps
                return False
            timestamps.append(now)
            self._buckets[client_ip] = timestamps
            return True


_RATE_LIMITER = RateLimiter(max_requests=RATE_LIMIT_MAX, window_seconds=RATE_LIMIT_WINDOW)


def _load_history() -> None:
    """Load persisted score history from disk into _HISTORY deque on startup."""
    try:
        with open(HISTORY_FILE) as f:
            saved = json.load(f)
        with _HISTORY_LOCK:
            for item in saved[-144:]:
                _HISTORY.append(item)
        logger.info("History: loaded %d snapshot(s) from history.json", len(_HISTORY))
    except FileNotFoundError:
        logger.info("No history.json found — starting fresh.")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("history.json corrupt (%s) — starting fresh.", exc)


def _save_history(snapshot: list) -> None:
    """Atomically persist history to disk. Must NOT hold _HISTORY_LOCK when calling."""
    try:
        dir_ = os.path.dirname(HISTORY_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".history_tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(snapshot, f)
            shutil.move(tmp_path, HISTORY_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("Failed to save history.json")


def _do_recompute() -> dict:
    """Fetch fresh data, update cache, broadcast SSE, record history.

    Must be called while *not* holding _DASHBOARD_LOCK.
    Returns the freshly computed data dict with ``stale=False``.
    """
    with _METRICS_LOCK:
        _METRICS["cache_misses"] += 1

    data = compute_dashboard()

    # Score delta vs. last snapshot; suppressed for invalid feeds to avoid fake collapses.
    prev_total = None
    if data.get("data_quality", {}).get("valid", True):
        with _HISTORY_LOCK:
            prev_total = _HISTORY[-1]["total"] if _HISTORY else None
        data["score_delta"] = (data["total_score"] - prev_total
                               if prev_total is not None else None)
    else:
        data["score_delta"] = None

    data["stale"] = False

    with _DASHBOARD_LOCK:
        _DASHBOARD_CACHE["data"] = data
        _DASHBOARD_CACHE["ts"] = time.time()

    _sse_broadcast("dashboard", {
        "score":          data.get("total_score"),
        "previous_score": prev_total,
        "decision":       data.get("decision"),
        "ts":             data.get("ts"),
    })

    # Record in history only when live data is trustworthy.
    if data.get("data_quality", {}).get("valid", True):
        now_ts = time.time()
        snapshot = {
            "ts":  time.strftime("%H:%M", time.gmtime()),
            "total": data["total_score"],
            "v":  data["pillars"]["volatility"]["score"],
            "tr": data["pillars"]["trend"]["score"],
            "br": data["pillars"]["breadth"]["score"],
            "mo": data["pillars"]["momentum"]["score"],
            "ma": data["pillars"]["macro"]["score"],
        }
        history_copy = None
        with _HISTORY_LOCK:
            if (not _HISTORY or _HISTORY[-1]["total"] != snapshot["total"]
                    or now_ts - _HISTORY_META["last_ts"] > 300):
                _HISTORY.append(snapshot)
                _HISTORY_META["last_ts"] = now_ts
                history_copy = list(_HISTORY)
        if history_copy is not None:
            _save_history(history_copy)

    return data


def _background_recompute() -> None:
    """Background thread: refresh stale cache without blocking any request."""
    try:
        with _COMPUTE_LOCK:
            # Another thread may have refreshed while we waited for the lock.
            with _DASHBOARD_LOCK:
                if time.time() - _DASHBOARD_CACHE["ts"] < _DASHBOARD_TTL:
                    return
            _do_recompute()
    except Exception:
        logger.exception("Background recompute failed")
    finally:
        _RECOMPUTING.clear()


def get_cached_dashboard() -> dict:
    with _METRICS_LOCK:
        _METRICS["requests"] += 1

    # ── Fast path ── cache is fresh; return immediately.
    with _DASHBOARD_LOCK:
        now = time.time()
        if _DASHBOARD_CACHE["data"] and now - _DASHBOARD_CACHE["ts"] < _DASHBOARD_TTL:
            with _METRICS_LOCK:
                _METRICS["cache_hits"] += 1
            return _DASHBOARD_CACHE["data"]

    # ── Stale-while-revalidate ── cache exists but is expired.
    # Return the last known result right now; kick off a background refresh
    # so the *next* request gets fresh data without any client waiting.
    with _DASHBOARD_LOCK:
        stale_data = _DASHBOARD_CACHE["data"]
        should_spawn = False
        if stale_data is not None and not _RECOMPUTING.is_set():
            _RECOMPUTING.set()   # atomic check-and-set under _DASHBOARD_LOCK
            should_spawn = True

    if stale_data is not None:
        with _METRICS_LOCK:
            _METRICS["cache_hits"] += 1
        if should_spawn:
            threading.Thread(
                target=_background_recompute, daemon=True, name="recompute"
            ).start()
        return {**stale_data, "stale": True}

    # ── Cold start ── no data at all; must block once (only on first boot).
    with _COMPUTE_LOCK:
        # Re-check: another thread may have finished while we waited.
        with _DASHBOARD_LOCK:
            if _DASHBOARD_CACHE["data"] and time.time() - _DASHBOARD_CACHE["ts"] < _DASHBOARD_TTL:
                with _METRICS_LOCK:
                    _METRICS["cache_hits"] += 1
                return _DASHBOARD_CACHE["data"]
        return _do_recompute()


def get_cached_watchlist_health(filename: str | None = None) -> dict:
    from watchlist import DEFAULT_WATCHLIST, WATCHLIST_DIR
    # Resolve path; fall back to default when no filename given
    if filename:
        # Safety: only allow plain filenames (no path separators)
        if os.sep in filename or "/" in filename or "\\" in filename:
            raise ValueError("Invalid watchlist filename")
        path = os.path.join(WATCHLIST_DIR, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Watchlist '{filename}' not found")
    else:
        path = DEFAULT_WATCHLIST
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        current_mtime = 0.0

    with _WATCHLIST_LOCK:
        now = time.time()
        file_unchanged = current_mtime == _WATCHLIST_CACHE["mtime"]
        cached_path = _WATCHLIST_CACHE.get("path")
        if (_WATCHLIST_CACHE["data"] and file_unchanged
                and cached_path == path
                and now - _WATCHLIST_CACHE["ts"] < _WATCHLIST_TTL):
            return _WATCHLIST_CACHE["data"]

    # Warm dashboard cache for regime context before scoring watchlist.
    with _DASHBOARD_LOCK:
        dash = _DASHBOARD_CACHE.get("data")
    if not dash:
        try:
            dash = get_cached_dashboard()
        except Exception:
            logger.exception("Failed to warm dashboard for watchlist regime context.")
            dash = {}
    try:
        spy_above_200 = dash.get("pillars", {}).get("trend", {}).get("details", {}).get("above_200", True)
        regime_known  = bool(dash)
    except Exception:
        logger.warning("Could not extract regime from dashboard; defaulting spy_above_200=True.")
        spy_above_200 = True
        regime_known  = False

    data = compute_watchlist_health(path=path, spy_above_200=spy_above_200)
    data["regime_known"] = regime_known
    with _WATCHLIST_LOCK:
        _WATCHLIST_CACHE["data"] = data
        _WATCHLIST_CACHE["ts"] = time.time()
        _WATCHLIST_CACHE["mtime"] = current_mtime
        _WATCHLIST_CACHE["path"] = path
    return data


def list_watchlist_files() -> list[str]:
    """Return sorted list of .txt filenames in the watchlists/ directory."""
    from watchlist import WATCHLIST_DIR
    try:
        return sorted(
            f for f in os.listdir(WATCHLIST_DIR)
            if f.lower().endswith(".txt") and os.path.isfile(os.path.join(WATCHLIST_DIR, f))
        )
    except OSError:
        return []


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
        self.send_header("Access-Control-Allow-Origin", _ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, status: int = 200):
        body = json.dumps(obj).encode()
        accept_enc = self.headers.get("Accept-Encoding", "")
        use_gzip = "gzip" in accept_enc and len(body) > 1024
        if use_gzip:
            body = gzip.compress(body, compresslevel=6)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _file(self, path: str, ctype: str = "text/html; charset=utf-8"):
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

    def _sse_stream(self):
        """Keep the connection open and push `dashboard` events via SSE."""
        client_queue: queue.Queue = queue.Queue(maxsize=10)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        with _SSE_LOCK:
            _SSE_CLIENTS.append(client_queue)
        logger.debug("SSE client connected (%d total)", len(_SSE_CLIENTS))
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    payload = client_queue.get(timeout=SSE_KEEPALIVE_SECS)
                    self.wfile.write(payload.encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Keepalive comment so proxies/browsers don't time out
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _SSE_LOCK:
                try:
                    _SSE_CLIENTS.remove(client_queue)
                except ValueError:
                    pass
            logger.debug("SSE client disconnected (%d remaining)", len(_SSE_CLIENTS))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ── rate limit /api/* endpoints ────────────────────────────────────
        if path.startswith("/api/"):
            client_ip = self.client_address[0]
            if not _RATE_LIMITER.is_allowed(client_ip):
                logger.warning("Rate limit exceeded for %s", client_ip)
                self._json({"error": "Rate limit exceeded. Max 30 requests/minute."}, 429)
                return

        # ── dashboard ──────────────────────────────────────────────────────
        if path == "/api/dashboard":
            try:
                self._json(get_cached_dashboard())
            except Exception:
                logger.exception("Error serving /api/dashboard")
                with _METRICS_LOCK:
                    _METRICS["errors"] += 1
                self._json({"error": "Internal server error"}, 500)
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
                use_ai = "ai=1" in (parsed.query or "")
                self._json(roundtable(data, use_ai=use_ai))
            except Exception:
                logger.exception("Error serving /api/analysis")
                with _METRICS_LOCK:
                    _METRICS["errors"] += 1
                self._json({"error": "Internal server error"}, 500)
            return

        # ── TradingView watchlist health ───────────────────────────────────
        if path == "/api/watchlist-health":
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            filename = params.get("file", [None])[0]
            try:
                self._json(get_cached_watchlist_health(filename=filename))
            except (ValueError, FileNotFoundError) as e:
                self._json({"error": str(e)}, 400)
            except Exception:
                logger.exception("Error serving /api/watchlist-health")
                with _METRICS_LOCK:
                    _METRICS["errors"] += 1
                self._json({"error": "Internal server error"}, 500)
            return

        # ── available watchlist files ──────────────────────────────────────
        if path == "/api/watchlists":
            from watchlist import DEFAULT_WATCHLIST
            default = os.path.basename(DEFAULT_WATCHLIST)
            self._json({"files": list_watchlist_files(), "default": default})
            return

        # ── Server-Sent Events stream ──────────────────────────────────────
        if path == "/api/stream":
            self._sse_stream()
            return

        # ── health check ───────────────────────────────────────────────────
        if path == "/health":
            with _DASHBOARD_LOCK:
                cache_age = (round(time.time() - _DASHBOARD_CACHE["ts"], 1)
                             if _DASHBOARD_CACHE["ts"] else None)
                cache_valid = _DASHBOARD_CACHE["data"] is not None
            with _HISTORY_LOCK:
                history_len = len(_HISTORY)
            self._json({
                "status": "ok",
                "uptime_seconds": round(time.time() - _SERVER_START),
                "dashboard_cache_age_seconds": cache_age,
                "dashboard_cache_valid": cache_valid,
                "dashboard_ttl_seconds": _DASHBOARD_TTL,
                "history_snapshots": history_len,
            })
            return

        # ── metrics ────────────────────────────────────────────────────────
        if path == "/metrics":
            with _METRICS_LOCK:
                stats = dict(_METRICS)
            self._json({
                "uptime_seconds": round(time.time() - _SERVER_START),
                **stats,
            })
            return

        # ── html routes ────────────────────────────────────────────────────
        if path in ("/", "/index.html", "/v5", "/v5/"):
            self._file(os.path.join(SCRIPT_DIR, HTML_FILE))
            return

        # ── static files (path-traversal-safe) ────────────────────────────
        joined = os.path.join(SCRIPT_DIR, path.lstrip("/"))
        static_path = os.path.realpath(joined)
        # Ensure resolved path stays inside SCRIPT_DIR
        if not static_path.startswith(os.path.realpath(SCRIPT_DIR) + os.sep):
            self._json({"error": "forbidden"}, 403)
            return
        if os.path.isfile(static_path):
            ext = path.rsplit(".", 1)[-1]
            types = {"html": "text/html", "js": "application/javascript",
                     "css": "text/css", "json": "application/json"}
            self._file(static_path, types.get(ext, "application/octet-stream"))
            return

        self._json({"error": "not found"}, 404)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    html = os.path.join(SCRIPT_DIR, HTML_FILE)
    missing = "" if os.path.exists(html) else f"  ⚠  {HTML_FILE} not found in this folder!\n"

    print("\n  ╔══════════════════════════════════════════════╗")
    print("  ║  Should I Trade?  ·  Market Quality v6       ║")
    print("  ║  5-Pillar Score + Desk Roundtable            ║")
    print("  ╚══════════════════════════════════════════════╝")
    if missing:
        print(f"\n{missing}")
    print(f"\n  URL:        http://localhost:{PORT}")
    print(f"  Data:       Yahoo → Stooq fallback (free, no key)")
    print(f"  AI:         Local 5-persona desk (no key)")
    print("\n  Press Ctrl+C to stop.\n")

    _load_history()

    # Only auto-open browser locally (would fail on a headless server)
    if not IS_PRODUCTION:
        threading.Thread(
            target=lambda: (time.sleep(1.2), webbrowser.open(f"http://localhost:{PORT}")),
            daemon=True,
        ).start()

    class _QuietServer(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
                return  # browser dropped connection — not an error
            super().handle_error(request, client_address)

    server = _QuietServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")


if __name__ == "__main__":
    main()
