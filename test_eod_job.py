"""test_eod_job.py — Offline tests for the standalone EOD runner."""
from __future__ import annotations
import os, sys, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eod_job


class TestEodJob(unittest.TestCase):

    def test_weekend_is_a_clean_noop(self):
        with patch("data.market_state", return_value={"state": "weekend"}), \
             patch("scoring.compute_dashboard") as mock_dash:
            self.assertEqual(eod_job.run(), 0)
            mock_dash.assert_not_called()

    def test_invalid_data_records_nothing_and_exits_1(self):
        with patch("data.market_state", return_value={"state": "afterhours"}), \
             patch("scoring.compute_dashboard",
                   return_value={"data_quality": {"valid": False}}), \
             patch("daily_history.record_daily_snapshot") as mock_snap, \
             patch("forecast_log.record_forecast") as mock_fc:
            self.assertEqual(eod_job.run(), 1)
            mock_snap.assert_not_called()
            mock_fc.assert_not_called()

    def test_trading_day_records_snapshot_forecast_and_grades(self):
        payload = {"data_quality": {"valid": True}, "total_score": 61,
                   "decision": "SELECTIVE",
                   "pillars": {p: {"score": 50} for p in
                               ("volatility", "trend", "breadth", "momentum", "macro")}}
        with patch("data.market_state", return_value={"state": "afterhours"}), \
             patch("scoring.compute_dashboard", return_value=payload), \
             patch("daily_history.record_daily_snapshot",
                   return_value={"date": "x"}) as mock_snap, \
             patch("forecast_log.record_forecast", return_value=True) as mock_fc, \
             patch("forecast_log.grade_pending", return_value=1) as mock_grade:
            self.assertEqual(eod_job.run(), 0)
            mock_snap.assert_called_once()
            mock_fc.assert_called_once()
            mock_grade.assert_called_once()


if __name__ == "__main__":
    unittest.main()
