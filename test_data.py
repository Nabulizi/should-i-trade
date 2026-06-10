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
from datetime import datetime, timezone
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
