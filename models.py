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
    prevClose: float | None
    change1d: float | None
    changePct: float | None
    open: float | None
    high: float | None
    low: float | None
    volume: int | None
    source: str
    trade_date: Any


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


class DashboardPillarResult(PillarResult):
    """Pillar payload embedded in the dashboard response."""

    weight: int


class DecisionBand(TypedDict):
    """Score band metadata returned to the frontend."""

    min: int
    decision: str
    color: str
    position: str
    action: str


# ── Dashboard ─────────────────────────────────────────────────────────────────

class _DashboardResultRequired(TypedDict):
    """Required payload returned by ``compute_dashboard()`` in scoring.py."""

    total_score: int
    raw_total_score: int
    safety_max_score: int | None
    decision: str
    decision_color: str
    position_size: str
    action_hint: str
    market_state: dict[str, Any]
    fomc: dict[str, Any]
    opex: dict[str, Any]
    season: dict[str, Any]
    earnings: dict[str, Any]
    econ_events: list[dict[str, Any]]
    econ_calendar_stale: bool
    fomc_calendar_stale: bool
    conflicts: list[dict[str, Any]]
    override_reasons: list[str]
    pillars: dict[str, DashboardPillarResult]
    ticker: list[dict[str, Any]]
    futures_tape: dict[str, Any]
    fear_greed_stock: dict[str, Any]
    fear_greed_crypto: dict[str, Any]
    spy_streak: dict[str, Any]
    timestamp: str
    data_sources: dict[str, str]
    data_coverage: dict[str, Any]
    data_quality: dict[str, Any]
    decision_bands: list[DecisionBand]


class DashboardResult(_DashboardResultRequired, total=False):
    """Full dashboard payload.

    ``server.py`` adds these optional runtime fields after ``compute_dashboard()``
    returns, before serializing the JSON response.
    """

    score_delta: int | None
    stale: bool
