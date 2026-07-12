"""test_watchlist.py — Offline unit tests for watchlist classification.

P0-023: symbols with insufficient history must read "No Data", never
"below 20/50/200d" — with a handful of bars every MA is None, which would
misclassify a perfectly healthy new listing as Broken/Avoid.
P0-024: the watchlist payload must not contain server filesystem paths.
"""
from __future__ import annotations
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WL_MIN_HISTORY_BARS
from watchlist import _classify, EXAMPLE_WATCHLIST_NAME, WATCHLIST_DIR


def _quote(price: float = 100.0) -> dict:
    return {"price": price, "changePct": 0.5, "source": "yahoo"}


def _closes(n: int, start: float = 50.0, step: float = 0.2) -> list[float]:
    return [start + i * step for i in range(n)]


class TestMinHistoryGate(unittest.TestCase):

    def test_short_history_is_no_data_not_broken(self):
        row = _classify("NEWIPO", "NYSE:NEWIPO", "equity",
                        _quote(100.0), _closes(WL_MIN_HISTORY_BARS - 1))
        self.assertEqual(row["bucket"], "unavailable")
        self.assertEqual(row["label"], "No Data")
        self.assertEqual(row["entry_state"], "No Data")
        self.assertIn("insufficient history", row["why"])
        self.assertNotIn("below", row["why"])

    def test_no_quote_is_no_data(self):
        row = _classify("XYZ", "NYSE:XYZ", "equity", None, _closes(220))
        self.assertEqual(row["bucket"], "unavailable")
        self.assertEqual(row["why"], "quote unavailable")

    def test_sufficient_history_is_classified(self):
        # 220 rising bars, price above all MAs → a real trend bucket
        closes = _closes(220)
        row = _classify("AAPL", "NASDAQ:AAPL", "equity",
                        _quote(closes[-1] * 1.01), closes)
        self.assertNotEqual(row["bucket"], "unavailable")

    def test_boundary_exactly_min_bars_is_classified(self):
        closes = _closes(WL_MIN_HISTORY_BARS)
        row = _classify("AAPL", "NASDAQ:AAPL", "equity",
                        _quote(closes[-1]), closes)
        self.assertNotEqual(row["bucket"], "unavailable")


class TestPayloadPrivacy(unittest.TestCase):

    def test_payload_has_no_filesystem_path(self):
        """compute_watchlist_health must expose the basename only (P0-024)."""
        from unittest.mock import patch
        import watchlist as wl
        example = os.path.join(WATCHLIST_DIR, EXAMPLE_WATCHLIST_NAME)
        with patch.object(wl, "get_quote", return_value=None), \
             patch.object(wl, "get_history", return_value=[]):
            payload = wl.compute_watchlist_health(path=example)
        self.assertNotIn("path", payload)
        self.assertEqual(payload["name"], EXAMPLE_WATCHLIST_NAME)
        self.assertNotIn(os.sep + "watchlists", str(payload))


class TestDefaultWatchlist(unittest.TestCase):

    def test_example_watchlist_exists_and_is_tracked_default_fallback(self):
        self.assertTrue(os.path.isfile(os.path.join(WATCHLIST_DIR, EXAMPLE_WATCHLIST_NAME)))

    def test_default_prefers_personal_export(self):
        import tempfile
        import watchlist as wl
        with tempfile.TemporaryDirectory() as d:
            orig = wl.WATCHLIST_DIR
            wl.WATCHLIST_DIR = d
            try:
                open(os.path.join(d, EXAMPLE_WATCHLIST_NAME), "w").close()
                self.assertTrue(wl._default_watchlist().endswith(EXAMPLE_WATCHLIST_NAME))
                open(os.path.join(d, "My_List.txt"), "w").close()
                self.assertTrue(wl._default_watchlist().endswith("My_List.txt"))
            finally:
                wl.WATCHLIST_DIR = orig


if __name__ == "__main__":
    unittest.main()
