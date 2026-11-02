"""
test_data.py — Offline unit tests for data.py

Tests cover:
  • Circuit breaker state machine (closed → open → half-open → closed)
  • get_quote() fallback chain (yahoo→stooq, circuit interactions)
  • get_history() fallback chain (official→yahoo→stooq, circuit interactions)
  • list_watchlist_files() directory scanning

All tests are fully offline — yf_quote, stooq_quote, yf_history,
stooq_history, cboe_vix_history, and treasury_10y_history are patched
via unittest.mock so no network calls are made.
"""
from __future__ import annotations
import sys, time, unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# ── isolate config imports so tests work regardless of CWD ────────────────
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data
from data import (
    _cb_allow, _cb_success, _cb_failure, _CB, _CB_LOCK,
    get_quote, get_history,
)
from config import CB_FAILURE_THRESHOLD, CB_RESET_SECS

# ── helpers ───────────────────────────────────────────────────────────────
GOOD_QUOTE = {"price": 450.0, "prevClose": 445.0, "change1d": 5.0,
              "changePct": 1.12, "source": "yahoo"}
GOOD_HISTORY = list(range(1, 230))   # 229 closes — well above any minimum


def _reset_cb(symbol: str) -> None:
    """Reset circuit state for a symbol between tests."""
    with _CB_LOCK:
        _CB.pop(symbol, None)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Circuit-breaker unit tests (pure state machine)
# ═══════════════════════════════════════════════════════════════════════════
class TestCircuitBreakerStateMachine(unittest.TestCase):

    def setUp(self):
        _reset_cb("TEST")

    # ── initial state ──────────────────────────────────────────────────────
    def test_new_symbol_is_closed(self):
        self.assertTrue(_cb_allow("TEST"))

    def test_one_failure_still_closed(self):
        _cb_failure("TEST")
        self.assertTrue(_cb_allow("TEST"))

    def test_threshold_minus_one_still_closed(self):
        for _ in range(CB_FAILURE_THRESHOLD - 1):
            _cb_failure("TEST")
        self.assertTrue(_cb_allow("TEST"))

    # ── opening ────────────────────────────────────────────────────────────
    def test_opens_at_threshold(self):
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("TEST")
        self.assertFalse(_cb_allow("TEST"))

    def test_stays_open_before_reset(self):
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("TEST")
        # Verify it stays closed for several more checks
        for _ in range(5):
            self.assertFalse(_cb_allow("TEST"))

    # ── half-open ─────────────────────────────────────────────────────────
    def test_half_opens_after_reset_period(self):
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("TEST")
        # Back-date the opened_at to simulate elapsed time
        with _CB_LOCK:
            _CB["TEST"]["opened_at"] = time.time() - CB_RESET_SECS - 1
        self.assertTrue(_cb_allow("TEST"))  # HALF-OPEN: probe allowed

    def test_half_open_failure_reopens(self):
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("TEST")
        with _CB_LOCK:
            _CB["TEST"]["opened_at"] = time.time() - CB_RESET_SECS - 1
        _cb_allow("TEST")   # transitions to HALF-OPEN (clears opened_at)
        _cb_failure("TEST")  # probe failed → OPEN again
        self.assertFalse(_cb_allow("TEST"))

    # ── success resets ────────────────────────────────────────────────────
    def test_success_resets_failures(self):
        for _ in range(CB_FAILURE_THRESHOLD - 1):
            _cb_failure("TEST")
        _cb_success("TEST")
        with _CB_LOCK:
            state = _CB.get("TEST", {})
        self.assertEqual(state.get("failures", 0), 0)
        self.assertIsNone(state.get("opened_at"))

    def test_success_closes_open_circuit(self):
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("TEST")
        self.assertFalse(_cb_allow("TEST"))
        _cb_success("TEST")
        self.assertTrue(_cb_allow("TEST"))

    def test_unknown_symbol_success_is_safe(self):
        _reset_cb("NEVER_SEEN")
        _cb_success("NEVER_SEEN")
        self.assertTrue(_cb_allow("NEVER_SEEN"))

    # ── threshold config ──────────────────────────────────────────────────
    def test_threshold_is_configurable(self):
        """CB_FAILURE_THRESHOLD from config.py governs when circuit opens."""
        self.assertGreater(CB_FAILURE_THRESHOLD, 0)
        # After exactly threshold failures the circuit must be open
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("TEST")
        self.assertFalse(_cb_allow("TEST"))


# ═══════════════════════════════════════════════════════════════════════════
# 2. get_quote() fallback chain
# ═══════════════════════════════════════════════════════════════════════════
class TestGetQuoteFallback(unittest.TestCase):

    def setUp(self):
        _reset_cb("SPY")

    @patch("data.yf_quote", return_value=GOOD_QUOTE)
    def test_yahoo_success_returned(self, mock_yf):
        q = get_quote("SPY")
        self.assertEqual(q["price"], 450.0)
        mock_yf.assert_called_once_with("SPY")

    @patch("data.stooq_quote", return_value=GOOD_QUOTE)
    @patch("data.yf_quote",    return_value=None)
    def test_falls_back_to_stooq_when_yahoo_none(self, mock_yf, mock_stooq):
        q = get_quote("SPY")
        self.assertIsNotNone(q)
        mock_stooq.assert_called_once_with("SPY")

    @patch("data.stooq_quote", return_value=None)
    @patch("data.yf_quote",    return_value=None)
    def test_returns_none_when_both_fail(self, _yf, _stooq):
        q = get_quote("SPY")
        self.assertIsNone(q)

    @patch("data.stooq_quote", return_value=None)
    @patch("data.yf_quote",    return_value=None)
    def test_failure_increments_cb(self, _yf, _stooq):
        _reset_cb("SPY")
        for _ in range(CB_FAILURE_THRESHOLD):
            get_quote("SPY")
        self.assertFalse(_cb_allow("SPY"))

    @patch("data.yf_quote", return_value=GOOD_QUOTE)
    def test_success_resets_cb(self, _yf):
        # Pre-open circuit
        for _ in range(CB_FAILURE_THRESHOLD - 1):
            _cb_failure("SPY")
        get_quote("SPY")
        with _CB_LOCK:
            state = _CB.get("SPY", {})
        self.assertEqual(state.get("failures", 0), 0)

    @patch("data.yf_quote")
    @patch("data.stooq_quote")
    def test_open_circuit_returns_none_no_network(self, mock_stooq, mock_yf):
        """When circuit is OPEN, no fetch functions should be called."""
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("SPY")
        result = get_quote("SPY")
        self.assertIsNone(result)
        mock_yf.assert_not_called()
        mock_stooq.assert_not_called()

    @patch("data.yf_quote", side_effect=RuntimeError("network error"))
    @patch("data.stooq_quote", return_value=None)
    def test_exception_in_yf_quote_handled(self, _stooq, _yf):
        q = get_quote("SPY")
        self.assertIsNone(q)   # exception swallowed, returns None


# ═══════════════════════════════════════════════════════════════════════════
# 3. get_history() fallback chain
# ═══════════════════════════════════════════════════════════════════════════
class TestGetHistoryFallback(unittest.TestCase):

    def setUp(self):
        _reset_cb("SPY")
        _reset_cb("^VIX")
        _reset_cb("^TNX")

    @patch("data.yf_history", return_value=GOOD_HISTORY)
    def test_yahoo_history_returned(self, mock_yf):
        h = get_history("SPY")
        self.assertEqual(len(h), len(GOOD_HISTORY))
        mock_yf.assert_called_once()

    @patch("data.stooq_history", return_value=GOOD_HISTORY)
    @patch("data.yf_history",    return_value=[])
    def test_falls_back_to_stooq(self, _yf, mock_stooq):
        h = get_history("SPY")
        self.assertTrue(len(h) > 0)

    @patch("data.stooq_history", return_value=[])
    @patch("data.yf_history",    return_value=[])
    def test_returns_empty_when_all_fail(self, _yf, _stooq):
        h = get_history("SPY")
        self.assertEqual(h, [])

    @patch("data.cboe_vix_history", return_value=GOOD_HISTORY)
    def test_vix_uses_cboe_primary_source(self, mock_cboe):
        # _OFFICIAL_SOURCES holds a direct reference — patch it too
        import data as _d
        orig = _d._OFFICIAL_SOURCES.get("^VIX")
        _d._OFFICIAL_SOURCES["^VIX"] = mock_cboe
        try:
            h = get_history("^VIX")
            mock_cboe.assert_called_once()
            self.assertEqual(len(h), len(GOOD_HISTORY))
        finally:
            _d._OFFICIAL_SOURCES["^VIX"] = orig

    @patch("data.yf_history",       return_value=GOOD_HISTORY)
    @patch("data.cboe_vix_history",  return_value=[])   # CBOE fails
    def test_vix_falls_back_to_yahoo_if_cboe_empty(self, mock_cboe, mock_yf):
        import data as _d
        orig = _d._OFFICIAL_SOURCES.get("^VIX")
        _d._OFFICIAL_SOURCES["^VIX"] = mock_cboe
        try:
            h = get_history("^VIX")
            mock_yf.assert_called_once()
            self.assertTrue(len(h) > 0)
        finally:
            _d._OFFICIAL_SOURCES["^VIX"] = orig

    @patch("data.treasury_10y_history", return_value=GOOD_HISTORY)
    def test_tnx_uses_treasury_primary(self, mock_tsy):
        import data as _d
        orig = _d._OFFICIAL_SOURCES.get("^TNX")
        _d._OFFICIAL_SOURCES["^TNX"] = mock_tsy
        try:
            h = get_history("^TNX")
            mock_tsy.assert_called_once()
        finally:
            _d._OFFICIAL_SOURCES["^TNX"] = orig

    @patch("data.yf_history", side_effect=RuntimeError("boom"))
    @patch("data.stooq_history", return_value=[])
    def test_exception_in_history_returns_empty(self, _stooq, _yf):
        h = get_history("SPY")
        self.assertEqual(h, [])

    @patch("data.yf_history")
    @patch("data.stooq_history")
    def test_open_circuit_returns_empty_no_network(self, mock_stooq, mock_yf):
        for _ in range(CB_FAILURE_THRESHOLD):
            _cb_failure("SPY")
        h = get_history("SPY")
        self.assertEqual(h, [])
        mock_yf.assert_not_called()
        mock_stooq.assert_not_called()

    # ── P0-022: history-source provenance registry ────────────────────────
    @patch("data.yf_history", return_value=GOOD_HISTORY)
    def test_history_source_records_yahoo(self, _yf):
        import data as _d
        _d._HISTORY_SOURCE.pop("SPY", None)
        get_history("SPY")
        self.assertEqual(_d.history_source("SPY"), "yahoo")

    @patch("data.stooq_history", return_value=GOOD_HISTORY)
    @patch("data.yf_history",    return_value=[])
    def test_history_source_records_stooq_fallback(self, _yf, _stooq):
        import data as _d
        _d._HISTORY_SOURCE.pop("SPY", None)
        get_history("SPY")
        self.assertEqual(_d.history_source("SPY"), "stooq")

    @patch("data.cboe_vix_history", return_value=GOOD_HISTORY)
    def test_history_source_records_cboe(self, mock_cboe):
        import data as _d
        orig = _d._OFFICIAL_SOURCES.get("^VIX")
        _d._OFFICIAL_SOURCES["^VIX"] = mock_cboe
        _d._HISTORY_SOURCE.pop("^VIX", None)
        try:
            get_history("^VIX")
            self.assertEqual(_d.history_source("^VIX"), "cboe")
        finally:
            _d._OFFICIAL_SOURCES["^VIX"] = orig

    def test_history_source_unknown_symbol_is_none(self):
        import data as _d
        self.assertIsNone(_d.history_source("NEVER-FETCHED-XYZ"))


# ═══════════════════════════════════════════════════════════════════════════
# 4. list_watchlist_files()
# ═══════════════════════════════════════════════════════════════════════════
class TestListWatchlistFiles(unittest.TestCase):

    def test_returns_sorted_txt_files(self):
        import tempfile, os
        from server import list_watchlist_files
        with tempfile.TemporaryDirectory() as d:
            # Patch WATCHLIST_DIR via the watchlist module
            import watchlist as wl
            orig = wl.WATCHLIST_DIR
            wl.WATCHLIST_DIR = d
            try:
                # Create test files
                for name in ["Bravo.txt", "Alpha.txt", "notes.md", "Charlie.txt"]:
                    open(os.path.join(d, name), "w").close()
                files = list_watchlist_files()
                self.assertEqual(files, ["Alpha.txt", "Bravo.txt", "Charlie.txt"])
                self.assertNotIn("notes.md", files)   # non-.txt excluded
            finally:
                wl.WATCHLIST_DIR = orig

    def test_returns_empty_on_missing_dir(self):
        from server import list_watchlist_files
        import watchlist as wl
        orig = wl.WATCHLIST_DIR
        wl.WATCHLIST_DIR = "/tmp/nonexistent_watchlist_dir_xyz"
        try:
            files = list_watchlist_files()
            self.assertEqual(files, [])
        finally:
            wl.WATCHLIST_DIR = orig


# ═══════════════════════════════════════════════════════════════════════════
# 5. yf_quote / yf_history shape contracts
# ═══════════════════════════════════════════════════════════════════════════
class TestQuoteShapeContracts(unittest.TestCase):
    """Validate that successful quotes contain required fields."""

    def test_good_quote_has_required_keys(self):
        for key in ("price", "prevClose", "change1d", "changePct", "source"):
            self.assertIn(key, GOOD_QUOTE)

    def test_quote_prices_are_numeric(self):
        self.assertIsInstance(GOOD_QUOTE["price"],      float)
        self.assertIsInstance(GOOD_QUOTE["changePct"],  float)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Calendar freshness
# ═══════════════════════════════════════════════════════════════════════════
class TestCalendarFreshness(unittest.TestCase):
    """Fail before hand-maintained economic/FOMC calendars silently expire."""

    MIN_FUTURE_DAYS = 90

    def _days_until(self, date_str: str) -> int:
        last = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        return (last - today).days

    def test_economic_calendar_has_future_coverage(self):
        days = self._days_until(data._ECON_CALENDAR_LAST)
        self.assertGreaterEqual(
            days,
            self.MIN_FUTURE_DAYS,
            f"_ECON_CALENDAR expires in {days} days; extend data.py before it goes stale.",
        )

    def test_fomc_calendar_has_future_coverage(self):
        days = self._days_until(data._FOMC_LAST)
        self.assertGreaterEqual(
            days,
            self.MIN_FUTURE_DAYS,
            f"_FOMC_2026_2027 expires in {days} days; extend data.py before it goes stale.",
        )


class TestExtendedEconCalendar(unittest.TestCase):
    """Tier-2 releases are derived from fixed rules, so pin the rules."""

    def test_claims_are_thursdays_shifting_off_holidays(self):
        # Thanksgiving 2026 falls Thu Nov 26 -> claims move to Wed Nov 25.
        events = data.econ_calendar_extended(date(2026, 11, 20), date(2026, 11, 30))
        claims = [e[0] for e in events if e[1] == "CLAIMS"]
        self.assertEqual(claims, ["2026-11-25"])

        # A normal week keeps Thursday.
        events = data.econ_calendar_extended(date(2026, 8, 3), date(2026, 8, 9))
        claims = [e[0] for e in events if e[1] == "CLAIMS"]
        self.assertEqual(claims, ["2026-08-06"])

    def test_ism_uses_business_days_not_calendar_days(self):
        # Jan 1 2027 is a holiday and Jan 2-3 a weekend, so the 1st business
        # day is Mon Jan 4 and the 3rd is Wed Jan 6.
        events = data.econ_calendar_extended(date(2027, 1, 1), date(2027, 1, 10))
        by_type = {e[1]: e[0] for e in events}
        self.assertEqual(by_type["ISM_MFG"], "2027-01-04")
        self.assertEqual(by_type["ISM_SVC"], "2027-01-06")

    def test_window_merges_tiers_and_stays_sorted(self):
        events = data.econ_calendar_window(30)
        self.assertTrue(events, "expected at least one event in a 30-day window")
        self.assertEqual([e["date"] for e in events],
                         sorted(e["date"] for e in events))
        self.assertTrue({e["tier"] for e in events} <= {1, 2})

    def test_dashboard_calendar_is_unpolluted_by_tier2(self):
        # econ_proximity() drives the UI's "next 3 releases" and must keep
        # showing only the hand-verified tier-1 list.
        names = {e["name"] for e in data.econ_proximity()}
        self.assertFalse(names & {n for n, _ in data._TIER2_RULES.values()})


class TestTier1InflationDates(unittest.TestCase):
    """Pin the BLS-published CPI/PPI dates.

    The briefing routine treats tier 1 as ground truth, so a wrong date here
    is published as fact. These were inverted for September 2026 (CPI and PPI
    swapped) and drifted for Oct/Nov/Dec, because the list was filled in on the
    assumption that PPI always lands the day after CPI. It does not.
    Source: bls.gov/schedule/news_release/{cpi,ppi}.htm and the monthly pages.
    """

    BLS_2026_H2 = {
        "CPI": ["2026-09-11", "2026-10-14", "2026-11-10", "2026-12-10"],
        "PPI": ["2026-09-10", "2026-10-15", "2026-11-13", "2026-12-15"],
    }

    def test_matches_bls_schedule(self):
        for etype, expected in self.BLS_2026_H2.items():
            actual = [d for d, t, _ in data._ECON_CALENDAR
                      if t == etype and "2026-09-01" <= d <= "2026-12-31"]
            self.assertEqual(actual, expected, f"{etype} dates disagree with BLS")

    def test_september_ppi_precedes_cpi(self):
        # The specific inversion that shipped: guards against a "tidy up the
        # ordering" edit silently restoring CPI-then-PPI.
        sep = {t: d for d, t, _ in data._ECON_CALENDAR if d.startswith("2026-09")
               and t in ("CPI", "PPI")}
        self.assertLess(sep["PPI"], sep["CPI"])


class TestForwardCalendarRows(unittest.TestCase):
    """Rows still ahead as of Nov 2026, as published by the agencies. Tier 1 is
    treated as ground truth, so this guards against an edit drifting from them.
    Sources: bls.gov/schedule/news_release/{cpi,ppi,empsit}.htm and
    bea.gov/news/schedule (including /next-year), read 2026-11-01.
    """

    PUBLISHED = {
        "CPI": ["2026-11-10", "2026-12-10", "2027-01-13", "2027-02-11", "2027-03-10",
                "2027-04-13", "2027-05-12", "2027-06-10"],
        "PPI": ["2026-11-13", "2026-12-15", "2027-01-14", "2027-02-12", "2027-03-12",
                "2027-04-14", "2027-05-13", "2027-06-11"],
        "NFP": ["2026-11-06", "2026-12-04", "2027-01-08", "2027-02-05", "2027-03-05",
                "2027-04-02", "2027-05-07", "2027-06-04"],
        "GDP": ["2026-11-25", "2026-12-23", "2027-01-28", "2027-02-25", "2027-03-31",
                "2027-04-29", "2027-05-27", "2027-06-25"],
    }

    def test_rows_match_the_published_schedules(self):
        for etype, expected in self.PUBLISHED.items():
            actual = sorted(d for d, t, _ in data._ECON_CALENDAR
                            if t == etype and d >= "2026-11-01")
            self.assertEqual(actual, expected, etype)

    def test_coverage_warning_uses_the_real_last_date(self):
        self.assertEqual(data._ECON_CALENDAR_LAST,
                         max(d for d, _, _ in data._ECON_CALENDAR))


def _frozen_utc(*args):
    """A data.datetime whose now() is fixed, so et_now() and any direct UTC read
    both see the same instant. The real clock can't affect these tests."""
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(*args, tzinfo=timezone.utc)
    return patch("data.datetime", Frozen)


class TestCalendarsUseEasternDate(unittest.TestCase):
    """US release calendars run on the ET date. The UTC date rolls over at
    7-8 PM ET, which used to shift every countdown a day early each evening."""

    def test_event_tomorrow_is_not_called_today_in_the_evening(self):
        with _frozen_utc(2026, 11, 10, 1, 30):   # Nov 9, 8:30 PM ET
            cpi = next(e for e in data.econ_proximity() if e["type"] == "CPI")
        self.assertEqual(cpi["days_until"], 1)
        self.assertEqual(cpi["urgency"], "Tomorrow")

    def test_todays_event_stays_listed_in_the_evening(self):
        with _frozen_utc(2026, 11, 11, 1, 30):   # Nov 10, 8:30 PM ET
            dates = [e["date"] for e in data.econ_calendar_window(1) if e["type"] == "CPI"]
        self.assertEqual(dates, ["2026-11-10"])

    def test_fomc_countdown(self):
        with _frozen_utc(2026, 12, 9, 1, 30):    # Dec 8, 8:30 PM ET
            fomc = data.fomc_proximity()
        self.assertEqual(fomc["days_until"], 1)
        self.assertEqual(fomc["label"], "FOMC Tomorrow")

    def test_opex_countdown(self):
        with _frozen_utc(2026, 11, 20, 1, 30):   # Nov 19, 8:30 PM ET; OpEx is Nov 20
            self.assertEqual(data.opex_proximity()["days_until"], 1)

    def test_seasonality_month(self):
        with _frozen_utc(2026, 11, 1, 1, 0):     # Oct 31, 9 PM ET
            self.assertEqual(data.seasonality()["month"], 10)

    def test_earnings_season_start(self):
        ms, ds, _, _, _ = data._EARNINGS_WINDOWS[1]
        with _frozen_utc(2026, ms, ds, 1, 30):   # 8:30 or 9:30 PM ET the evening before
            self.assertFalse(data.earnings_season()["in_season"])
        with _frozen_utc(2026, ms, ds, 16, 0):   # noon on the first day
            self.assertTrue(data.earnings_season()["in_season"])

    def test_morning_reading_is_unchanged(self):
        with _frozen_utc(2026, 11, 9, 14, 0):    # Nov 9, 9 AM ET
            cpi = next(e for e in data.econ_proximity() if e["type"] == "CPI")
        self.assertEqual(cpi["days_until"], 1)


class TestEtNow(unittest.TestCase):
    """et_now() returns DST-aware US/Eastern wall-clock time."""

    def test_et_now_applies_dst_offset(self):
        with patch("data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            et = data.et_now()
        self.assertEqual(et.hour, 8)   # July = EDT = UTC-4

    def test_et_now_applies_standard_offset(self):
        with patch("data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            et = data.et_now()
        self.assertEqual(et.hour, 7)   # January = EST = UTC-5


# ═══════════════════════════════════════════════════════════════════════════
# Liquidity context (FRED) — fetch_url is the only thing faked; parsing is real
# ═══════════════════════════════════════════════════════════════════════════
FRED_IDS = ["WALCL", "WTREGEN", "RRPONTSYD", "DFII10", "DGS2",
            "DTWEXBGS", "BAMLH0A0HYM2", "NFCI", "DFF"]


def _fred_csv(series_id: str, rows: list[tuple[int, str]]) -> str:
    """CSV in FRED's real shape; rows are (days_ago, value)."""
    today = date.today()
    lines = [f"observation_date,{series_id}"]
    lines += [f"{today - timedelta(days=ago)},{v}" for ago, v in rows]
    return "\n".join(lines) + "\n"


def _flat_fred() -> dict:
    """Every series unchanged over the 4-week lookback (7 vs 35 days ago)."""
    return {
        "WALCL": [(98, "6800000"), (35, "6800000"), (7, "6800000")],  # $ millions
        "WTREGEN": [(98, "800000"), (35, "800000"), (7, "800000")],   # $ millions
        "RRPONTSYD": [(98, "100"), (35, "100"), (7, "100")],          # $ billions
        "DFII10": [(98, "2.00"), (35, "2.00"), (7, "2.00")],
        "DGS2": [(98, "4.00"), (35, "4.00"), (7, "4.00")],
        "DTWEXBGS": [(98, "120.00"), (35, "120.00"), (7, "120.00")],
        "BAMLH0A0HYM2": [(98, "3.00"), (35, "3.00"), (7, "3.00")],
        "NFCI": [(98, "-0.50"), (35, "-0.50"), (7, "-0.50")],
        "DFF": [(35, "4.00"), (7, "4.00")],
    }


class TestLiquidity(unittest.TestCase):

    def setUp(self):
        data._FRED_LAST_GOOD.clear()
        data._FRED_RETRY_AT.clear()
        data._CACHE.clear()

    def _run(self, **overrides):
        """overrides: series_id=rows, or series_id=None for a failed fetch."""
        fred = {**_flat_fred(), **overrides}

        def fake_fetch(url, **kw):
            sid = url.split("id=")[1].split("&")[0]
            rows = fred[sid]
            if rows is None:
                raise OSError("FRED down")
            return rows if isinstance(rows, str) else _fred_csv(sid, rows)

        with patch("data.fetch_url", side_effect=fake_fetch):
            return data.fetch_liquidity()

    def _item(self, result, key):
        return next(i for i in result["items"] if i["key"] == key)

    def test_net_liquidity_converts_rrp_billions_to_trillions(self):
        # 6.8T - 0.8T - 0.1T = 5.9T (RRP is published in billions, others millions)
        item = self._item(self._run(), "net_liquidity")
        self.assertEqual(item["value"], 5.9)
        self.assertEqual(item["direction"], "flat")

    def test_net_liquidity_rise_reads_as_loosening(self):
        # now 5.9T vs 6.7 - 0.9 - 0.2 = 5.6T four weeks ago
        item = self._item(self._run(
            WALCL=[(35, "6700000"), (7, "6800000")],
            WTREGEN=[(35, "900000"), (7, "800000")],
            RRPONTSYD=[(35, "200"), (7, "100")],
        ), "net_liquidity")
        self.assertEqual(item["change"], 0.3)
        self.assertEqual(item["direction"], "loosening")

    def test_net_liquidity_uses_rrp_as_of_the_balance_sheet_date(self):
        # A 500B RRP print newer than the last WALCL must not be subtracted.
        item = self._item(self._run(
            RRPONTSYD=[(35, "100"), (7, "100"), (2, "500")],
        ), "net_liquidity")
        self.assertEqual(item["value"], 5.9)

    def test_rising_rates_dollar_and_spreads_read_as_tightening(self):
        result = self._run(
            DFII10=[(35, "2.00"), (7, "2.30")],
            DGS2=[(35, "4.00"), (7, "4.30")],
            DTWEXBGS=[(35, "120.00"), (7, "123.00")],
            BAMLH0A0HYM2=[(35, "3.00"), (7, "3.50")],
            NFCI=[(35, "-0.50"), (7, "-0.30")],
        )
        for key in ("real_yield", "two_year", "dollar", "hy_spread", "nfci"):
            self.assertEqual(self._item(result, key)["direction"], "tightening", key)
        self.assertEqual(result["tone"], "Tightening")
        self.assertEqual(result["tightening"], 5)

    def test_yields_falling_together_are_not_enough_for_a_headline(self):
        # Real and 2Y move together, so a bond rally alone is 1 vote, not 2.
        result = self._run(
            DFII10=[(35, "2.30"), (7, "2.00")],
            DGS2=[(35, "4.30"), (7, "4.00")],
        )
        self.assertEqual(self._item(result, "two_year")["direction"], "loosening")
        self.assertEqual(result["loosening"], 2)
        self.assertEqual(result["loosening_votes"], 1)
        self.assertEqual(result["tone"], "Neutral")

    def test_yields_plus_one_other_series_make_a_headline(self):
        # 0.5 + 0.5 + 1 = 2 votes
        result = self._run(
            DFII10=[(35, "2.30"), (7, "2.00")],
            DGS2=[(35, "4.30"), (7, "4.00")],
            BAMLH0A0HYM2=[(35, "3.50"), (7, "3.00")],
        )
        self.assertEqual(result["loosening_votes"], 2)
        self.assertEqual(result["tone"], "Loosening")

    def test_hy_spread_level_tag_boundaries(self):
        for level, want in (("3.99", "Calm"), ("4.00", "Elevated"),
                            ("5.99", "Elevated"), ("6.00", "Stress")):
            item = self._item(self._run(BAMLH0A0HYM2=[(35, level), (7, level)]), "hy_spread")
            self.assertEqual(item["level"], want, level)

    def test_hy_spread_without_data_has_no_level_tag(self):
        item = self._item(self._run(BAMLH0A0HYM2=None), "hy_spread")
        self.assertIsNone(item["level"])

    def test_longer_reading_catches_a_trend_the_4_week_window_misses(self):
        # The jump happened 5+ weeks ago: flat over 4 weeks, tightening over 13.
        result = self._run(
            DFII10=[(98, "2.00"), (35, "2.40"), (7, "2.40")],
            DGS2=[(98, "4.00"), (35, "4.40"), (7, "4.40")],
            DTWEXBGS=[(98, "118.00"), (35, "122.00"), (7, "122.00")],
            BAMLH0A0HYM2=[(98, "2.60"), (35, "3.20"), (7, "3.20")],
        )
        self.assertEqual(result["tone"], "Neutral")
        self.assertEqual(result["longer"]["tone"], "Tightening")
        self.assertEqual(result["longer"]["tightening_votes"], 3)   # 0.5 + 0.5 + 1 + 1
        self.assertEqual(result["longer"]["lookback_weeks"], 13)

    def test_longer_reading_needs_enough_history(self):
        result = self._run(
            DFII10=[(35, "2.00"), (7, "2.00")], DGS2=[(35, "4.00"), (7, "4.00")],
            DTWEXBGS=[(35, "120.00"), (7, "120.00")],
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["longer"]["tone"], "Unavailable")

    def test_request_window_covers_the_longer_lookback(self):
        # 91-day lookback from a print up to 21 days old needs 112+ days.
        urls = []

        def fake(url, **kw):
            urls.append(url)
            return _fred_csv("DGS2", [(7, "4.00")])

        with patch("data.fetch_url", side_effect=fake):
            data.fred_series("DGS2")
        start = date.fromisoformat(urls[0].split("cosd=")[1])
        self.assertGreaterEqual((date.today() - start).days, 112)

    def test_loosening_is_not_shown_as_a_positive_signal(self):
        # The evidence is on the risk side: no green "go" for the headline.
        result = self._run(
            DGS2=[(98, "4.30"), (35, "4.30"), (7, "4.00")],
            DFII10=[(98, "2.30"), (35, "2.30"), (7, "2.00")],
            BAMLH0A0HYM2=[(98, "3.50"), (35, "3.50"), (7, "3.00")],
        )
        self.assertEqual(result["tone"], "Loosening")
        self.assertNotEqual(result["tone_color"], "green")

    def test_read_line_gives_the_history_for_the_current_reading(self):
        tight = self._run(
            DFII10=[(35, "2.00"), (7, "2.30")], DGS2=[(35, "4.00"), (7, "4.30")],
            DTWEXBGS=[(35, "120.00"), (7, "123.00")], NFCI=[(35, "-0.50"), (7, "-0.30")],
        )
        self.assertEqual(tight["tone"], "Tightening")
        self.assertIn("32%", tight["read"])
        self.assertIn("19%", tight["read"])
        loose = self._run(
            DFII10=[(35, "2.30"), (7, "2.00")], DGS2=[(35, "4.30"), (7, "4.00")],
            BAMLH0A0HYM2=[(35, "3.50"), (7, "3.00")],
        )
        self.assertIn("14%", loose["read"])
        neutral = self._run()
        self.assertEqual(neutral["tone"], "Neutral")
        self.assertNotIn("%", neutral["read"].split("share one vote.")[1].split("USD")[0])

    def test_summary_says_both_windows_in_one_sentence(self):
        for short, long, want in (
            ("Neutral", "Tightening", "Little change over 4 weeks, but tighter than 3 months ago."),
            ("Tightening", "Tightening", "Tightening over 4 weeks, and tighter than 3 months ago."),
            ("Loosening", "Tightening", "Easing over 4 weeks, but tighter than 3 months ago."),
            ("Tightening", "Loosening", "Tightening over 4 weeks, but easier than 3 months ago."),
            ("Neutral", "Neutral", "Little change over 4 weeks, and about the same as 3 months ago."),
            ("Loosening", "Unavailable", "Easing over 4 weeks."),
            ("Unavailable", "Tightening", None),
        ):
            self.assertEqual(data._liquidity_summary(short, long), want, (short, long))

    def test_payload_carries_the_summary(self):
        result = self._run()
        self.assertEqual(result["summary"],
                         "Little change over 4 weeks, and about the same as 3 months ago.")

    def test_no_summary_without_enough_series(self):
        down = self._run(DFII10=None, DGS2=None, DTWEXBGS=None)
        self.assertIsNone(down["summary"])

    def test_fed_path_compares_2y_with_fed_funds(self):
        for two_year, want_spread, want_lean in (("4.60", 0.6, "leans toward hikes"),
                                                 ("4.25", 0.25, "leans toward hikes"),
                                                 ("4.20", 0.2, "about flat"),
                                                 ("3.80", -0.2, "about flat"),
                                                 ("3.75", -0.25, "leans toward cuts"),
                                                 ("3.40", -0.6, "leans toward cuts")):
            path = self._run(DGS2=[(35, two_year), (7, two_year)])["fed_path"]
            self.assertEqual(path["spread"], want_spread, two_year)
            self.assertEqual(path["lean"], want_lean, two_year)

    def test_fed_path_does_not_vote(self):
        # A 2Y far above funds is a level, not a change: the headline stays Neutral.
        result = self._run(DGS2=[(98, "6.00"), (35, "6.00"), (7, "6.00")])
        self.assertEqual(result["fed_path"]["lean"], "leans toward hikes")
        self.assertEqual(result["tone"], "Neutral")
        self.assertEqual(result["tightening_votes"], 0)

    def test_fed_path_is_absent_when_either_rate_is_missing_or_stale(self):
        self.assertIsNone(self._run(DFF=None)["fed_path"])
        self.assertIsNone(self._run(DFF=[(60, "4.00"), (40, "4.00")])["fed_path"])
        self.assertIsNone(self._run(DGS2=None)["fed_path"])

    def test_small_move_is_flat_not_a_signal(self):
        result = self._run(DGS2=[(35, "4.00"), (7, "4.05")])
        self.assertEqual(self._item(result, "two_year")["direction"], "flat")

    def test_disagreement_is_neutral(self):
        result = self._run(
            DGS2=[(35, "4.30"), (7, "4.00")],           # loosening
            DTWEXBGS=[(35, "120.00"), (7, "123.00")],   # tightening
        )
        self.assertEqual(result["tone"], "Neutral")

    def test_one_failed_series_leaves_the_rest(self):
        result = self._run(NFCI=None)
        nfci = self._item(result, "nfci")
        self.assertFalse(nfci["available"])
        self.assertIsNone(nfci["direction"])
        self.assertTrue(result["valid"])
        self.assertTrue(self._item(result, "two_year")["available"])

    def test_any_net_liquidity_leg_missing_disables_that_item(self):
        result = self._run(RRPONTSYD=None)
        self.assertFalse(self._item(result, "net_liquidity")["available"])

    def test_too_few_series_gives_no_regime(self):
        result = self._run(DFII10=None, DGS2=None, DTWEXBGS=None)
        self.assertFalse(result["valid"])
        self.assertEqual(result["tone"], "Unavailable")
        self.assertEqual(result["tone_color"], "gray")

    def test_stale_series_is_not_read_as_current(self):
        # 40 days without a print (e.g. a release halted): show nothing as a signal.
        item = self._item(self._run(DGS2=[(70, "4.60"), (40, "4.00")]), "two_year")
        self.assertFalse(item["available"])
        self.assertIsNone(item["direction"])

    def test_missing_value_rows_are_skipped(self):
        # FRED leaves market holidays blank; the latest real print still counts.
        item = self._item(self._run(DGS2=[(35, "4.00"), (7, "4.30"), (6, ""), (5, ".")]),
                          "two_year")
        self.assertEqual(item["value"], 4.3)
        self.assertEqual(item["as_of"], (date.today() - timedelta(days=7)).isoformat())

    def test_html_error_page_counts_as_a_failed_fetch(self):
        result = self._run(DGS2="<html><body>Blocked</body></html>")
        self.assertFalse(self._item(result, "two_year")["available"])

    def test_request_avoids_the_browser_style_user_agent_fred_hangs_on(self):
        # Observed live: FRED hangs on Mozilla-style agents, accepts Python's default.
        sent = []

        def fake_urlopen(req, timeout=None):
            sent.append(req)
            resp = MagicMock()
            resp.__enter__.return_value.read.return_value = (
                _fred_csv("DGS2", [(35, "4.00"), (7, "4.30")]).encode())
            return resp

        with patch("data.urlopen", side_effect=fake_urlopen):
            self.assertEqual(data.fred_series("DGS2")[-1][1], 4.3)
        self.assertNotIn("Mozilla", sent[0].get_header("User-agent"))

    def test_failure_serves_last_good_and_pauses_retries(self):
        calls = []
        good = _fred_csv("DGS2", [(35, "4.00"), (7, "4.30")])

        def up(url, **kw):
            return good

        def down(url, **kw):
            calls.append(url)
            raise OSError("FRED down")

        with patch("data.fetch_url", side_effect=up):
            fresh = data.fred_series("DGS2")
        with patch("data.fetch_url", side_effect=down):
            for _ in range(5):
                self.assertEqual(data.fred_series("DGS2"), fresh)
        self.assertEqual(len(calls), 1)   # the outage costs one attempt, not five

    def test_retry_resumes_after_the_pause(self):
        calls = []

        def down(url, **kw):
            calls.append(url)
            raise OSError("FRED down")

        now = time.time()
        with patch("data.fetch_url", side_effect=down):
            with patch("time.time", return_value=now):
                data.fred_series("DGS2")
            with patch("time.time", return_value=now + 14 * 60):
                data.fred_series("DGS2")
            self.assertEqual(len(calls), 1)
            with patch("time.time", return_value=now + 16 * 60):
                data.fred_series("DGS2")
        self.assertEqual(len(calls), 2)

    def test_long_outage_stops_showing_the_old_direction(self):
        # The failure this panel must not have: last good data outliving the 21-day limit.
        rising = self._run(DGS2=[(35, "4.00"), (7, "4.30")])
        self.assertEqual(self._item(rising, "two_year")["direction"], "tightening")

        class Later(date):
            @classmethod
            def today(cls):
                return date.today() + timedelta(days=30)

        def down(url, **kw):
            raise OSError("FRED down")

        with patch("data.fetch_url", side_effect=down), patch("data.date", Later):
            result = data.fetch_liquidity()
        item = self._item(result, "two_year")
        self.assertFalse(item["available"])
        self.assertIsNone(item["direction"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["tone"], "Unavailable")

    def test_short_outage_keeps_the_last_good_reading(self):
        self._run(DGS2=[(35, "4.00"), (7, "4.30")])

        def down(url, **kw):
            raise OSError("FRED down")

        with patch("data.fetch_url", side_effect=down):
            item = self._item(data.fetch_liquidity(), "two_year")
        self.assertTrue(item["available"])
        self.assertEqual(item["direction"], "tightening")


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=0, stream=sys.stdout)
    result  = runner.run(suite)

    total  = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"\n{'='*55}")
    print(f"Results: {passed}/{total} passed  "
          f"{'✓  ALL PASS' if not result.failures and not result.errors else '✗  FAILURES'}")
    sys.exit(0 if result.wasSuccessful() else 1)
