"""test_forecast_log.py — Offline tests for the prospective forecast log.

Covers P3-001 (EOD record), P3-005..008 (predeclared outcome math),
P3-011 (idempotent, forecasts never mutated), P3-012 (audit integrity).
No network: bars are synthetic, files live in a temp dir.
"""
from __future__ import annotations
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import forecast_log as fl


def _dashboard(total=62, valid=True, version="v6.1") -> dict:
    return {
        "model_version": version,
        "total_score": total,
        "raw_total_score": total,
        "decision": "SELECTIVE",
        "natural_decision": "SELECTIVE",
        "data_quality": {"valid": valid},
        "as_of": {"calculated_at": "2026-07-10T16:05:00-04:00",
                  "market_data_as_of": "2026-07-10", "session": "afterhours",
                  "history_last_bar": "2026-07-10"},
        "pillars": {k: {"score": 50} for k in
                    ("volatility", "trend", "breadth", "momentum", "macro")},
        "reliability": {"level": "high", "coverage_pct": 100.0},
        "vol_target": {"exposure_pct": 60.0},
        "data_sources": {},
    }


_BARS = [
    {"date": "2026-07-09", "open": 99.0,  "high": 101.0, "low": 98.0,  "close": 100.0},
    {"date": "2026-07-10", "open": 100.5, "high": 102.0, "low": 99.5,  "close": 100.0},
    {"date": "2026-07-13", "open": 101.0, "high": 104.0, "low": 100.0, "close": 103.0},
]


class _TmpFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = (fl.FORECAST_FILE, fl.OUTCOME_FILE)
        fl.FORECAST_FILE = os.path.join(self._tmp.name, "forecasts.jsonl")
        fl.OUTCOME_FILE = os.path.join(self._tmp.name, "outcomes.jsonl")

    def tearDown(self):
        fl.FORECAST_FILE, fl.OUTCOME_FILE = self._orig
        self._tmp.cleanup()


class TestRecording(_TmpFiles):

    def test_record_is_idempotent(self):
        self.assertTrue(fl.record_forecast(_dashboard(), "2026-07-10"))
        self.assertFalse(fl.record_forecast(_dashboard(), "2026-07-10"))
        self.assertEqual(len(fl._read_jsonl(fl.FORECAST_FILE)), 1)

    def test_invalid_data_quality_is_not_a_forecast(self):
        self.assertFalse(fl.record_forecast(_dashboard(valid=False), "2026-07-10"))
        self.assertEqual(fl._read_jsonl(fl.FORECAST_FILE), [])

    def test_record_schema_and_hash(self):
        fl.record_forecast(_dashboard(), "2026-07-10")
        row = fl._read_jsonl(fl.FORECAST_FILE)[0]
        for key in ("forecast_date", "observation_track", "model_version",
                    "calculated_at", "market_data_as_of", "total_score",
                    "decision_band", "displayed_band", "pillars",
                    "reliability", "volatility_budget", "input_manifest_hash"):
            self.assertIn(key, row)
        self.assertEqual(row["input_manifest_hash"], fl._manifest_hash(row))

    def test_different_model_versions_do_not_collide(self):
        self.assertTrue(fl.record_forecast(_dashboard(version="v6.1"), "2026-07-10"))
        self.assertTrue(fl.record_forecast(_dashboard(version="v7.0"), "2026-07-10"))
        self.assertEqual(len(fl._read_jsonl(fl.FORECAST_FILE)), 2)


class TestOutcomeMath(_TmpFiles):
    """Predeclared formulas (docs/prospective-log.md) — P3-005..P3-008."""

    def test_outcome_values(self):
        fl.record_forecast(_dashboard(), "2026-07-10")
        fc = fl._read_jsonl(fl.FORECAST_FILE)[0]
        out = fl.compute_outcome(fc, _BARS)
        # C0=100; next bar: O 101, H 104, L 100, C 103
        self.assertEqual(out["next_bar_date"], "2026-07-13")
        self.assertAlmostEqual(out["next_return_pct"], 3.0)
        self.assertAlmostEqual(out["range_size_pct"], 4.0)
        self.assertAlmostEqual(out["range_efficiency"], 0.5)   # |103-101|/4
        self.assertAlmostEqual(out["favorable_excursion_pct"], 4.0)
        self.assertAlmostEqual(out["adverse_excursion_pct"], 0.0)
        self.assertTrue(out["large_move"])                      # 3.0 >= 1.5

    def test_flat_bar_efficiency_is_none(self):
        bars = _BARS[:2] + [{"date": "2026-07-13", "open": 100.0, "high": 100.0,
                             "low": 100.0, "close": 100.0}]
        fl.record_forecast(_dashboard(), "2026-07-10")
        out = fl.compute_outcome(fl._read_jsonl(fl.FORECAST_FILE)[0], bars)
        self.assertIsNone(out["range_efficiency"])
        self.assertFalse(out["large_move"])

    def test_no_next_bar_stays_ungraded(self):
        fl.record_forecast(_dashboard(), "2026-07-10")
        fc = fl._read_jsonl(fl.FORECAST_FILE)[0]
        self.assertIsNone(fl.compute_outcome(fc, _BARS[:2]))   # no bar after 07-10
        self.assertIsNone(fl.compute_outcome(fc, []))


class TestGrading(_TmpFiles):

    def test_grade_pending_is_idempotent_and_never_mutates_forecasts(self):
        fl.record_forecast(_dashboard(), "2026-07-10")
        before = open(fl.FORECAST_FILE).read()
        self.assertEqual(fl.grade_pending(bars=_BARS), 1)
        self.assertEqual(fl.grade_pending(bars=_BARS), 0)      # already graded
        self.assertEqual(open(fl.FORECAST_FILE).read(), before)
        self.assertEqual(len(fl._read_jsonl(fl.OUTCOME_FILE)), 1)

    def test_ungradeable_forecast_waits(self):
        fl.record_forecast(_dashboard(), "2026-07-13")          # last bar → no next
        self.assertEqual(fl.grade_pending(bars=_BARS), 0)
        self.assertEqual(fl._read_jsonl(fl.OUTCOME_FILE), [])


class TestAudit(_TmpFiles):

    def test_clean_log_passes(self):
        fl.record_forecast(_dashboard(), "2026-07-10")
        report = fl.audit()
        self.assertTrue(report["ok"])
        self.assertEqual(report["tampered"], [])
        self.assertEqual(report["duplicates"], [])

    def test_tampered_record_is_flagged(self):
        fl.record_forecast(_dashboard(total=62), "2026-07-10")
        row = fl._read_jsonl(fl.FORECAST_FILE)[0]
        row["total_score"] = 95                                 # edit after the fact
        with open(fl.FORECAST_FILE, "w") as f:
            f.write(json.dumps(row) + "\n")
        report = fl.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(report["tampered"], ["2026-07-10"])

    def test_gap_between_forecasts_is_reported(self):
        fl.record_forecast(_dashboard(), "2026-07-01")
        fl.record_forecast(_dashboard(), "2026-07-10")          # > 4 calendar days
        report = fl.audit()
        self.assertEqual(report["gaps"], ["2026-07-01 → 2026-07-10"])

    def test_status_shape(self):
        fl.record_forecast(_dashboard(), "2026-07-10")
        st = fl.status()
        self.assertEqual(st["count"], 1)
        self.assertEqual(st["last_forecast_date"], "2026-07-10")
        self.assertEqual(st["track"], "eod")


if __name__ == "__main__":
    unittest.main()
