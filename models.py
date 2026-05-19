"""
models.py — Shared TypedDict schemas for Should I Trade?

TypedDicts give IDE autocomplete and let static analysers (mypy / pyright)
catch key typos at analysis time with zero runtime overhead.

Note: named 'models.py' (not 'types.py') to avoid shadowing the stdlib
'types' module which is used by test stubs.
"""

from __future__ import annotations

from typing import Any, TypedDict


# ── Market data ───────────────────────────────────────────────────────────────

class Quote(TypedDict, total=False):
    """Minimal quote dict produced by data.py fetch functions.

    ``total=False`` because not every field is guaranteed on every source;
    callers should use ``q.get("price")`` rather than ``q["price"]``.
    """

    price: float | None
    changePct: float | None
    open: float | None
    high: float | None
    low: float | None
    volume: int | None
    source: str


# ── Scoring ───────────────────────────────────────────────────────────────────

class PillarResult(TypedDict):
    """Return type for every ``score_*`` function in scoring.py.

    - ``score``: clamped integer 0–100
    - ``details``: pillar-specific metrics dict (keys vary per pillar)
    - ``reasons``: ordered ``["+N label", "-N label", ...]`` explanation strings
    """

    score: int
    details: dict[str, Any]
    reasons: list[str]


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardResult(TypedDict):
    """Full payload returned by ``compute_dashboard()`` in scoring.py."""

    score: int
    decision: str
    decision_color: str
    position: str
    pillars: dict[str, PillarResult]
    data_quality: dict[str, Any]
    market_state: dict[str, Any]
    fomc: dict[str, Any]
    econ: list[dict[str, Any]]
    opex: dict[str, Any]
    seasonality: dict[str, Any]
    earnings_season: dict[str, Any]
    conflicts: list[dict[str, Any]]
    roundtable: list[dict[str, Any]]
    ts: float
