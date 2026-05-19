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
