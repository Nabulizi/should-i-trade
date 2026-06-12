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

class MarketState(TypedDict):
    """Current US cash-session state shown in the header."""

    state: str
    label: str
    color: str
    et_time: str
    et_date: str


class CalendarOverlay(TypedDict, total=False):
    """Calendar/risk overlay payloads with source-specific optional fields."""

    days_until: int | None
    date_pretty: str
    label: str
    color: str
    kind: str
    score_adj: int
    bias: str
    in_season: bool


class EconEvent(TypedDict, total=False):
    """Upcoming economic calendar event."""

    type: str
    name: str
    days_until: int | None
    date_pretty: str
    color: str


class Conflict(TypedDict, total=False):
    """A mixed-signal warning surfaced by the scoring engine."""

    label: str
    message: str
    severity: str


class TickerItem(TypedDict):
    """Single item in the scrolling market ticker."""

    symbol: str
    price: float
    change_pct: float
    up: bool


class FuturesTape(TypedDict, total=False):
    """Pre-market / futures context. Missing fields imply unavailable data."""

    valid: bool
    label: str
    color: str
    items: list[dict[str, Any]]
    reason: str


class FearGreed(TypedDict, total=False):
    """Fear/greed source payload. Providers may omit unavailable fields."""

    available: bool
    value: int | float
    label: str
    color: str
    source: str


class SpyStreak(TypedDict):
    """Consecutive SPY up/down-day streak."""

    direction: str
    days: int


class DataSources(TypedDict):
    """Provider labels for the headline data inputs."""

    vix: str
    tnx: str
    spy: str
    btc: str


class DataCoverage(TypedDict):
    """Raw quote coverage from the dashboard fetch phase."""

    requested: int
    fetched: int
    failed: list[str]


class CriticalHistoryMissing(TypedDict):
    """Missing core history requirement that disables the decision."""

    symbol: str
    required: int
    found: int


class DataQuality(TypedDict):
    """Decision-grade data validation result."""

    valid: bool
    coverage_pct: float
    min_coverage_pct: int
    critical_symbols: list[str]
    critical_missing: list[str]
    critical_history_requirements: dict[str, int]
    critical_history_missing: list[CriticalHistoryMissing]
    sector_history_valid: int
    sector_history_required: int
    sector_history_min_points: int
    message: str


class VolTargetInfo(TypedDict):
    """Evidence-backed vol-target exposure dial (see docs/backtest-report.md)."""

    exposure_pct: float
    realized_vol_pct: float


class _DashboardResultRequired(TypedDict):
    """Required payload returned by ``compute_dashboard()`` in scoring.py."""

    total_score: int
    raw_total_score: int
    safety_max_score: int | None
    decision: str
    decision_color: str
    position_size: str
    action_hint: str
    market_state: MarketState
    fomc: CalendarOverlay
    opex: CalendarOverlay
    season: CalendarOverlay
    earnings: CalendarOverlay
    econ_events: list[EconEvent]
    econ_calendar_stale: bool
    fomc_calendar_stale: bool
    conflicts: list[Conflict]
    override_reasons: list[str]
    pillars: dict[str, DashboardPillarResult]
    ticker: list[TickerItem]
    futures_tape: FuturesTape
    fear_greed_stock: FearGreed
    fear_greed_crypto: FearGreed
    spy_streak: SpyStreak
    vol_target: VolTargetInfo | None
    timestamp: str
    data_sources: DataSources
    data_coverage: DataCoverage
    data_quality: DataQuality
    decision_bands: list[DecisionBand]


class DashboardResult(_DashboardResultRequired, total=False):
    """Full dashboard payload.

    ``server.py`` adds these optional runtime fields after ``compute_dashboard()``
    returns, before serializing the JSON response.
    """

    score_delta: int | None
    stale: bool
