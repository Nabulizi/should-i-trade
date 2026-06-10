"""
config.py — User-tunable settings for Should I Trade?

Edit this file to adjust port, cache refresh rates, pillar weights, or
rate-limiting without touching any logic files.  All values here are
imported by server.py and scoring.py at startup.
"""

from __future__ import annotations

# ── Server ────────────────────────────────────────────────────────────────────

PORT: int = 8765
"""TCP port the HTTP server listens on.  Change here if 8765 is taken."""

# ── Cache TTLs ────────────────────────────────────────────────────────────────

DASHBOARD_TTL: int = 60
"""Seconds between full market-data refreshes (one complete scoring cycle)."""

WATCHLIST_TTL: int = 300
"""Seconds between watchlist health recomputes."""

HISTORY_MAXLEN: int = 144
"""Maximum score snapshots kept in memory / history.json (~12 h at 5-min intervals)."""

# ── Rate Limiting (sliding-window, per-IP) ────────────────────────────────────

RATE_LIMIT_MAX: int = 30
"""Maximum API requests allowed per IP within RATE_LIMIT_WINDOW seconds."""

RATE_LIMIT_WINDOW: int = 60
"""Sliding-window duration in seconds for the rate limiter."""

# ── Pillar Weights ────────────────────────────────────────────────────────────
# Must sum to 1.0.  Adjusting weights shifts how much each market dimension
# influences the composite Market Quality Score.

PILLAR_WEIGHTS: dict[str, float] = {
    "volatility": 0.15,
    "trend":      0.30,
    "breadth":    0.25,
    "momentum":   0.20,
    "macro":      0.10,
}

# ── AI Synthesis (optional) ──────────────────────────────────────────────────

GEMINI_API_KEY: str = ""
"""Google Gemini API key for AI-powered Desk Head synthesis (free tier).
   Get a free key at https://aistudio.google.com  (1 500 req/day, no credit card).
   Leave empty to use the rule-based fallback — everything still works.

   ⚠ Do NOT paste your key here — this file is tracked by git.
   Set it via the GEMINI_API_KEY environment variable (takes priority),
   or create a git-ignored config_local.py next to this file containing:
       GEMINI_API_KEY = "your-key-here"
"""

# ── Circuit Breaker (data.py) ─────────────────────────────────────────────────

CB_FAILURE_THRESHOLD: int = 3
"""Consecutive fetch failures before a symbol's circuit opens."""

CB_RESET_SECS: int = 60
"""Seconds a circuit stays OPEN before transitioning to HALF-OPEN for a probe."""

# ── SSE ───────────────────────────────────────────────────────────────────────

SSE_KEEPALIVE_SECS: int = 30
"""How often the SSE stream sends a keepalive comment to prevent proxy timeouts."""

# ── Watchlist Scoring Thresholds ─────────────────────────────────────────────
# Used by watchlist.py to classify symbols as "near MA" or "extended".

WL_MA20_NEAR_PCT: float = 3.5
"""Symbol counts as 'near' its 20d MA when within this % distance."""

WL_MA50_NEAR_PCT: float = 4.0
"""Symbol counts as 'near' its 50d MA when within this % distance."""

WL_EXTENDED_RSI: float = 72
"""RSI(14) above this marks a symbol as extended."""

WL_EXTENDED_DIST: float = 0.08
"""Price more than this fraction above the 20d MA marks a symbol as extended."""

# ── Local Overrides (git-ignored) ─────────────────────────────────────────────
# Put machine-specific secrets/settings (e.g. GEMINI_API_KEY) in a
# config_local.py next to this file. It is listed in .gitignore so a pasted
# API key can never be committed by accident.
try:
    from config_local import *  # type: ignore[import-not-found]  # noqa: F401,F403,E402
except ImportError:
    pass
