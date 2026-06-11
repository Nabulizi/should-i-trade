"""test_backtest_report.py - Offline contracts for Markdown backtest reporting."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_report


FIXTURE_CSV = """date,total,raw_total,decision,above_200,v,tr,br,mo,ma,rsi2,dist20,fwd1,fwd5,fwd20
2024-01-02,40,40,DE-RISK,False,45,35,40,38,50,12.0,-1.2,-0.5,-1.0,-2.0
2024-01-03,55,55,SELECTIVE,True,60,58,54,55,50,45.0,0.1,0.2,0.6,1.0
2024-01-04,65,65,SELECTIVE,True,70,65,60,68,54,55.0,0.4,0.1,0.9,1.4
2024-01-05,72,72,CONSTRUCTIVE,True,75,72,70,71,65,62.0,0.7,0.3,1.1,2.0
2024-01-08,88,88,RISK-ON,True,90,89,86,88,78,70.0,1.1,0.4,1.6,2.8
2024-01-09,35,35,RISK-OFF,False,40,30,35,30,48,9.0,-1.6,-0.7,-1.4,-2.5
2024-01-10,58,58,SELECTIVE,True,64,60,55,58,52,50.0,0.2,0.1,0.5,0.8
2024-01-11,74,74,CONSTRUCTIVE,True,76,75,72,74,66,64.0,0.8,0.3,1.3,2.2
2024-01-12,92,92,RISK-ON,True,92,94,89,91,80,76.0,1.4,0.5,1.8,3.0
2024-01-16,45,45,DE-RISK,False,50,43,45,41,49,20.0,-0.8,-0.2,-0.7,-1.5
2024-01-17,57,57,SELECTIVE,True,61,59,58,56,51,48.0,0.0,0.2,0.7,1.1
2024-01-18,76,76,CONSTRUCTIVE,True,78,77,73,75,67,66.0,0.9,0.4,1.4,2.4
2024-01-19,90,90,RISK-ON,True,94,91,88,90,79,74.0,1.3,0.6,1.7,2.9
2024-01-22,42,42,DE-RISK,False,48,40,42,39,47,18.0,-0.9,-0.3,-0.8,-1.6
2024-01-23,60,60,SELECTIVE,True,66,62,59,60,53,52.0,0.3,0.2,0.8,1.2
2024-01-24,78,78,CONSTRUCTIVE,True,80,79,76,77,68,68.0,1.0,0.5,1.5,2.6
2024-01-25,94,94,RISK-ON,True,95,95,92,93,82,78.0,1.5,0.7,1.9,3.2
2024-01-26,38,38,RISK-OFF,False,42,36,38,35,46,11.0,-1.3,-0.6,-1.2,-2.2
2024-01-29,62,62,SELECTIVE,True,68,64,61,62,54,54.0,0.4,0.2,0.9,1.3
2024-01-30,80,80,CONSTRUCTIVE,True,82,81,78,80,70,70.0,1.1,0.5,1.6,2.7
2024-01-31,96,96,RISK-ON,True,96,97,94,95,84,80.0,1.6,0.8,2.0,3.4
2024-02-01,44,44,DE-RISK,False,49,42,44,40,48,19.0,-0.7,-0.2,-0.6,-1.4
2024-02-02,64,64,SELECTIVE,True,69,66,63,64,55,56.0,0.5,0.3,1.0,1.5
2024-02-05,82,82,CONSTRUCTIVE,True,84,83,80,82,72,72.0,1.2,0.6,1.7,2.8
2024-02-06,98,98,RISK-ON,True,98,98,96,97,86,82.0,1.7,0.9,2.1,3.6
2024-02-07,36,36,RISK-OFF,False,41,34,36,33,45,10.0,-1.4,-0.7,-1.3,-2.4
2024-02-08,66,66,SELECTIVE,True,71,68,65,66,56,58.0,0.6,0.3,1.1,1.6
2024-02-09,84,84,CONSTRUCTIVE,True,86,85,82,84,74,74.0,1.3,0.7,1.8,2.9
2024-02-12,99,99,RISK-ON,True,99,99,98,98,88,84.0,1.8,1.0,2.2,3.8
2024-02-13,46,46,DE-RISK,False,51,44,46,42,49,21.0,-0.6,-0.1,-0.5,-1.2
"""


class TestBacktestReport(unittest.TestCase):

    def test_load_rows_parses_contract_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["decision"], "DE-RISK")
        self.assertFalse(rows[0]["above_200"])
        self.assertEqual(rows[-1]["date"], "2024-02-13")
        self.assertIsInstance(rows[0]["total"], float)

    def test_build_report_contains_product_sections_and_strategy_rows(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)
            report = backtest_report.build_report(rows, "fixture.csv")

        self.assertIn("# Backtest Report", report)
        self.assertIn("## Executive Readout", report)
        self.assertIn("## Strategy Comparison", report)
        self.assertIn("Score >= 55 (SELECTIVE+)", report)
        self.assertIn("Buy & hold", report)
        self.assertIn("risk/exposure dial", report)
        # New sections — removing any of these fails CI
        self.assertIn("matched benchmark", report)
        self.assertIn("Mean/Std", report)
        self.assertIn("Generated", report)

    def test_strategy_score_55_has_less_than_full_exposure(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        strat = backtest_report.strategy(
            rows, "Score >= 55", lambda row: row["total"] >= 55)

        self.assertGreater(strat["total_return_pct"], 0)
        self.assertGreater(strat["exposure_pct"], 0)
        self.assertLess(strat["exposure_pct"], 100)

    def test_write_report_creates_markdown_file(self):
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "fixture.csv"
            output_path = Path(td) / "report.md"
            input_path.write_text(FIXTURE_CSV, encoding="utf-8")

            written = backtest_report.write_report(input_path, output_path)

            self.assertEqual(written, output_path)
            self.assertTrue(output_path.exists())
            self.assertIn("## Information Coefficient", output_path.read_text(encoding="utf-8"))

    def test_matched_benchmark_sharpe_equals_buy_and_hold_sharpe(self):
        """Constant scaling leaves mean/std invariant, so matched Sharpe == B&H Sharpe."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        strats = backtest_report.strategy_rows(rows)
        # indices: 0=constructive, 1=matched-constructive, 2=selective, 3=matched-selective, 4=bnh
        buy_hold_sharpe = strats[4]["sharpe"]
        for matched_idx in (1, 3):
            self.assertAlmostEqual(
                strats[matched_idx]["sharpe"], buy_hold_sharpe, places=9,
                msg=f"Matched benchmark at index {matched_idx} Sharpe should equal B&H Sharpe",
            )

    def test_matched_benchmark_exposure_equals_timing_strategy_exposure(self):
        """The matched baseline holds exactly the same exposure fraction as the timing rule."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        strats = backtest_report.strategy_rows(rows)
        self.assertAlmostEqual(strats[0]["exposure_pct"], strats[1]["exposure_pct"], places=6)
        self.assertAlmostEqual(strats[2]["exposure_pct"], strats[3]["exposure_pct"], places=6)

    def test_matched_benchmark_drawdown_shallower_than_full_buy_and_hold(self):
        """A de-leveraged constant-fraction baseline can never draw down deeper than 100% B&H."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(FIXTURE_CSV, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        strats = backtest_report.strategy_rows(rows)
        buy_hold_dd = strats[4]["max_drawdown_pct"]  # negative number
        for matched_idx in (1, 3):
            self.assertGreater(
                strats[matched_idx]["max_drawdown_pct"], buy_hold_dd,
                msg=f"Matched benchmark at index {matched_idx} should draw down less than 100% B&H",
            )

    def test_cross_window_matched_fractions_differ(self):
        """Matched benchmark recomputes exposure per window, not globally.

        Low-score rows (exposure ~0% for Score>=55) are placed before 2016-01-01
        and high-score rows (exposure ~100%) after. The matched fraction in the
        validation window must differ from the full-sample fraction.
        """
        # Build a CSV with low scores pre-2016 and high scores post-2016.
        pre = "\n".join(
            f"2015-01-{d:02d},30,30,DE-RISK,False,30,28,30,29,45,10.0,-1.0,-0.5,-1.0,-2.0"
            for d in range(2, 32)
        )
        post = "\n".join(
            f"2016-01-{d:02d},80,80,CONSTRUCTIVE,True,82,80,78,80,70,68.0,1.0,0.5,1.5,2.5"
            for d in range(2, 32)
        )
        csv_data = (
            "date,total,raw_total,decision,above_200,v,tr,br,mo,ma,"
            "rsi2,dist20,fwd1,fwd5,fwd20\n" + pre + "\n" + post
        )

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "split.csv"
            path.write_text(csv_data, encoding="utf-8")
            rows = backtest_report.load_rows(path)

        full_strats = backtest_report.strategy_rows(rows)
        validation_rows = [r for r in rows if r["date"] >= "2016-01-01"]
        val_strats = backtest_report.strategy_rows(validation_rows)

        full_selective_exposure = full_strats[2]["exposure_pct"]
        val_selective_exposure = val_strats[2]["exposure_pct"]

        self.assertNotAlmostEqual(
            full_selective_exposure, val_selective_exposure, places=1,
            msg="Cross-window exposures should differ when pre/post 2016 score distributions differ",
        )
        # Matched baselines must track their own window's timing strategy
        self.assertAlmostEqual(full_strats[2]["exposure_pct"], full_strats[3]["exposure_pct"], places=6)
        self.assertAlmostEqual(val_strats[2]["exposure_pct"], val_strats[3]["exposure_pct"], places=6)


if __name__ == "__main__":
    unittest.main()
