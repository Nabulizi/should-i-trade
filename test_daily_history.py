"""test_daily_history.py — offline tests for the per-trading-day snapshot store.

Covers: record/load roundtrip, same-date replacement, invalid-data skip,
maxlen cap, yesterday lookup, corrupt-file recovery. Fully offline.
"""
from __future__ import annotations
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import daily_history
from daily_history import load_daily_history, record_daily_snapshot, yesterday_snapshot


def _payload(total=72, decision="CONSTRUCTIVE", valid=True):
    return {
        "total_score": total, "decision": decision,
        "data_quality": {"valid": valid},
        "pillars": {p: {"score": s} for p, s in zip(
            ("volatility", "trend", "breadth", "momentum", "macro"),
            (88, 72, 88, 50, 61))},
    }


class TestDailyHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "daily_history.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_and_load_roundtrip(self):
        snap = record_daily_snapshot(_payload(), "2026-07-02", path=self.path)
        self.assertEqual(snap["total"], 72)
        self.assertEqual(snap["decision"], "CONSTRUCTIVE")
        self.assertEqual(snap["pillars"]["trend"], 72)
        self.assertEqual(load_daily_history(self.path), [snap])

    def test_same_date_replaces(self):
        record_daily_snapshot(_payload(total=70), "2026-07-02", path=self.path)
        record_daily_snapshot(_payload(total=75), "2026-07-02", path=self.path)
        hist = load_daily_history(self.path)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["total"], 75)

    def test_invalid_data_skipped(self):
        self.assertIsNone(
            record_daily_snapshot(_payload(valid=False), "2026-07-02", path=self.path))
        self.assertEqual(load_daily_history(self.path), [])

    def test_maxlen_cap(self):
        for i in range(daily_history.DAILY_HISTORY_MAXLEN + 5):
            record_daily_snapshot(_payload(), f"2026-{i:04d}", path=self.path)
        self.assertEqual(len(load_daily_history(self.path)),
                         daily_history.DAILY_HISTORY_MAXLEN)

    def test_yesterday_snapshot_picks_latest_before_today(self):
        record_daily_snapshot(_payload(total=60), "2026-07-01", path=self.path)
        record_daily_snapshot(_payload(total=68), "2026-07-02", path=self.path)
        record_daily_snapshot(_payload(total=72), "2026-07-03", path=self.path)
        y = yesterday_snapshot("2026-07-03", path=self.path)
        self.assertEqual(y["total"], 68)
        self.assertIsNone(yesterday_snapshot("2026-07-01", path=self.path))

    def test_missing_file_loads_empty(self):
        self.assertEqual(load_daily_history(self.path), [])

    def test_corrupt_file_recovers_empty(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(load_daily_history(self.path), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
