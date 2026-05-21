"""
Contract tests for the NEW analysis.py (TradingAgents integration).

These tests define the expected interface BEFORE implementation.
Some will fail until the new analysis.py is written — that is intentional.
"""

import unittest
import time
import threading
from unittest.mock import patch, MagicMock
import analysis

MINIMAL_DASHBOARD = {
    "ticker": "SPY",
    "composite_score": 65,
    "pillars": {
        "trend": {"score": 65, "details": {
            "above_20": True, "above_50": True, "above_200": False,
            "regime": "Bull", "ath_dist": 5, "rsi14": 55,
            "spy_change_pct": 0.5, "macd_hist": 0.1, "macd_label": "bullish",
            "char_label": "Trending"
        }},
        "volatility": {"score": 60, "details": {"vix": 18, "vix_label": "Moderate", "vix_pct": 0.4}},
        "breadth": {"score": 55, "details": {"advance_decline": 1.2, "highs52": 150, "lows52": 50, "pct_above_50ma": 60}},
        "momentum": {"score": 70, "details": {"rsi": 58, "macd_label": "bullish", "spy_ytd": 12}},
        "macro": {"score": 60, "details": {"fed_bias": "hold", "yield_curve": "flat", "sector_rotation": "neutral"}}
    }
}


class TestAnalysisNew(unittest.TestCase):
    def setUp(self):
        if hasattr(analysis, '_ROUNDTABLE_CACHE'):
            analysis._ROUNDTABLE_CACHE['ts'] = 0.0
            analysis._ROUNDTABLE_CACHE['data'] = None
        if hasattr(analysis, '_REFRESH_RUNNING'):
            analysis._REFRESH_RUNNING.clear()

    # ── Test 1 ──────────────────────────────────────────────────────────────
    def test_cache_attributes_exist(self):
        """Module must export _ROUNDTABLE_CACHE dict and _REFRESH_RUNNING Event."""
        self.assertTrue(hasattr(analysis, '_ROUNDTABLE_CACHE'),
                        "analysis._ROUNDTABLE_CACHE not found")
        self.assertTrue(hasattr(analysis, '_REFRESH_RUNNING'),
                        "analysis._REFRESH_RUNNING not found")

    # ── Test 2 ──────────────────────────────────────────────────────────────
    def test_roundtable_returns_quickly(self):
        """roundtable() must return in < 1 second (non-blocking contract)."""
        with patch.dict('os.environ', {}, clear=False):
            # Remove ANTHROPIC_API_KEY if present so fallback path is taken
            import os
            os.environ.pop('ANTHROPIC_API_KEY', None)
            start = time.time()
            analysis.roundtable(MINIMAL_DASHBOARD)
            elapsed = time.time() - start
        self.assertLess(elapsed, 1.0,
                        f"roundtable() took {elapsed:.2f}s — must be non-blocking (< 1s)")

    # ── Test 3 ──────────────────────────────────────────────────────────────
    def test_output_schema(self):
        """Return value must be {personas: [...5 dicts...], timestamp: str}."""
        with patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('ANTHROPIC_API_KEY', None)
            result = analysis.roundtable(MINIMAL_DASHBOARD)

        self.assertIsInstance(result, dict)
        self.assertIn("personas", result)
        self.assertIn("timestamp", result)
        self.assertEqual(len(result["personas"]), 5,
                         f"Expected 5 personas, got {len(result['personas'])}")

        required_keys = {"persona", "role", "avatar", "stance", "stance_color",
                         "read", "points", "verdict"}
        for i, p in enumerate(result["personas"]):
            missing = required_keys - p.keys()
            self.assertFalse(missing, f"Persona {i} missing keys: {missing}")

    # ── Test 4 ──────────────────────────────────────────────────────────────
    def test_cache_hit_returns_cached_result(self):
        """When cache is fresh, roundtable() must return it without calling legacy."""
        fake_result = {
            "personas": [
                {"persona": "FakeBot", "role": "test", "avatar": "🤖",
                 "stance": "Bullish", "stance_color": "green",
                 "read": "cached", "points": [], "verdict": "ok"}
            ] * 5,
            "timestamp": "12:00 UTC"
        }
        analysis._ROUNDTABLE_CACHE["data"] = fake_result
        analysis._ROUNDTABLE_CACHE["ts"] = time.time()  # fresh — < 1800s old

        result = analysis.roundtable({})  # empty dashboard; cache should be used
        self.assertIs(result, fake_result,
                      "Expected cached result to be returned unchanged")

    # ── Test 5 ──────────────────────────────────────────────────────────────
    def test_fallback_used_when_no_api_key(self):
        """With no ANTHROPIC_API_KEY, roundtable() must delegate to analysis_legacy."""
        import analysis_legacy
        sentinel = {"personas": [], "timestamp": "SENTINEL"}

        with patch.dict('os.environ', {}, clear=False):
            import os
            os.environ.pop('ANTHROPIC_API_KEY', None)
            with patch.object(analysis_legacy, 'roundtable', return_value=sentinel) as mock_legacy:
                result = analysis.roundtable(MINIMAL_DASHBOARD)

        mock_legacy.assert_called_once()
        self.assertEqual(result, sentinel,
                         "Expected legacy sentinel value to be returned")

    # ── Test 6 ──────────────────────────────────────────────────────────────
    def test_refresh_not_started_when_already_running(self):
        """When _REFRESH_RUNNING is set, no new Thread must be spawned."""
        analysis._REFRESH_RUNNING.set()  # mark refresh as already in progress

        with patch('threading.Thread') as mock_thread:
            analysis.roundtable(MINIMAL_DASHBOARD)

        mock_thread.assert_not_called()


if __name__ == '__main__':
    unittest.main()
