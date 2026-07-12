"""test_notify.py — offline tests for the morning push report.

Covers: delta formatting, band-change detection, Markdown report content,
Telegram/Discord senders (mocked urllib), push gating, scheduler due-logic.
Fully offline — urllib.request.urlopen is always mocked.
"""
from __future__ import annotations
import json, os, sys, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import notify
from notify import build_report, band_changed, _fmt_delta


def _payload(total=72, decision="CONSTRUCTIVE", valid=True):
    return {
        "total_score": total, "decision": decision,
        "data_quality": {"valid": valid, "message": "2 of 33 symbols failed"},
        "market_state": {"et_date": "Fri Jul 04", "et_time": "09:00 ET"},
        "pillars": {p: {"score": s} for p, s in zip(
            ("volatility", "trend", "breadth", "momentum", "macro"),
            (88, 72, 88, 50, 61))},
        "econ_events": [],
        "fomc": {"days_until": 25, "date_pretty": "Jul 29"},
    }


def _yesterday(total=68, decision="SELECTIVE"):
    return {"date": "2026-07-03", "total": total, "decision": decision,
            "pillars": {"volatility": 88, "trend": 69, "breadth": 82,
                        "momentum": 52, "macro": 61}}


class TestFmtDelta(unittest.TestCase):
    def test_up_down_flat_none(self):
        self.assertEqual(_fmt_delta(72, 68), "▲ +4")
        self.assertEqual(_fmt_delta(60, 65), "▼ -5")
        self.assertEqual(_fmt_delta(60, 60), "—")
        self.assertEqual(_fmt_delta(60, None), "")


class TestBandChanged(unittest.TestCase):
    def test_changed_and_unchanged_and_missing(self):
        self.assertTrue(band_changed(_payload(), _yesterday()))
        self.assertFalse(band_changed(_payload(decision="SELECTIVE"), _yesterday()))
        self.assertFalse(band_changed(_payload(), None))


class TestNoiseFraming(unittest.TestCase):
    """P1-031: small day-over-day deltas are labeled as typical noise."""

    def test_small_delta_same_band_flagged_as_noise(self):
        import notify, config
        data = _payload(total=60, decision="SELECTIVE")
        yday = _yesterday(total=60 - config.SCORE_NOISE_DELTA_1D, decision="SELECTIVE")
        report = notify.build_report(data, yday)
        self.assertIn("typical daily noise", report)

    def test_large_delta_not_flagged(self):
        import notify, config
        data = _payload(total=80, decision="CONSTRUCTIVE")
        yday = _yesterday(total=80 - config.SCORE_NOISE_DELTA_1D - 10, decision="SELECTIVE")
        report = notify.build_report(data, yday)
        self.assertNotIn("typical daily noise", report)


class TestBuildReport(unittest.TestCase):
    def test_full_report_contains_score_delta_bands_pillars(self):
        text = build_report(_payload(), _yesterday())
        self.assertIn("Score 72", text)
        self.assertIn("▲ +4", text)
        self.assertIn("CONSTRUCTIVE", text)
        self.assertIn("SELECTIVE → CONSTRUCTIVE", text)
        self.assertIn("Trend 72 (▲ +3)", text)
        self.assertIn(config.DASHBOARD_URL, text)

    def test_no_yesterday_omits_deltas_and_transition(self):
        text = build_report(_payload(), None)
        self.assertNotIn("→", text)
        self.assertNotIn("▲", text)
        self.assertIn("Score 72", text)

    def test_degraded_data_flagged(self):
        text = build_report(_payload(valid=False), _yesterday())
        self.assertIn("⚠", text)
        self.assertIn("2 of 33 symbols failed", text)

    def test_near_events_included_far_events_omitted(self):
        data = _payload()
        data["econ_events"] = [
            {"name": "CPI", "date_pretty": "Jul 06", "days_until": 2},
            {"name": "PPI", "date_pretty": "Jul 20", "days_until": 16},
        ]
        data["fomc"] = {"days_until": 2, "date_pretty": "Jul 06"}
        text = build_report(data, None)
        self.assertIn("CPI", text)
        self.assertNotIn("PPI", text)
        self.assertIn("FOMC", text)


class TestSenders(unittest.TestCase):
    def setUp(self):
        # Hermetic isolation: a developer's real config_local.py (or env)
        # must never leak into these tests — or worse, send real messages.
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL"):
            p = patch.object(config, key, "", create=True)
            p.start()
            self.addCleanup(p.stop)
        envp = patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "",
                                       "TELEGRAM_CHAT_ID": "",
                                       "DISCORD_WEBHOOK_URL": ""})
        envp.start()
        self.addCleanup(envp.stop)

    def _mock_urlopen(self):
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: resp
        resp.__exit__ = MagicMock(return_value=False)
        return patch("notify.urllib.request.urlopen", return_value=resp)

    def test_telegram_posts_token_chat_and_text(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok123",
                                     "TELEGRAM_CHAT_ID": "42"}):
            with self._mock_urlopen() as mock_open:
                self.assertTrue(notify.send_telegram("hello"))
        req = mock_open.call_args[0][0]
        self.assertIn("bottok123/sendMessage", req.full_url)
        body = json.loads(req.data.decode())
        self.assertEqual(body["chat_id"], "42")
        self.assertEqual(body["text"], "hello")

    def test_discord_posts_content(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://d/hook"}):
            with self._mock_urlopen() as mock_open:
                self.assertTrue(notify.send_discord("hello"))
        req = mock_open.call_args[0][0]
        self.assertEqual(req.full_url, "https://d/hook")
        self.assertEqual(json.loads(req.data.decode())["content"], "hello")
        # Cloudflare 403s the default Python-urllib UA — must send a real one.
        self.assertIn("ShouldITrade", req.get_header("User-agent", ""))

    def test_failure_logged_not_raised_retries_once(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://d/hook"}):
            with patch("notify.urllib.request.urlopen",
                       side_effect=OSError("boom")) as m:
                self.assertFalse(notify.send_discord("hello"))
        self.assertEqual(m.call_count, 2)   # one retry

    def test_push_report_counts_configured_channels_only(self):
        env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c",
               "DISCORD_WEBHOOK_URL": ""}
        with patch.dict(os.environ, env):
            with self._mock_urlopen():
                self.assertEqual(notify.push_report("msg"), 1)

    def test_push_report_zero_when_unconfigured(self):
        with patch("notify.urllib.request.urlopen") as m:
            self.assertEqual(notify.push_report("msg"), 0)
        m.assert_not_called()   # nothing configured → no network, ever

    def test_band_change_gate(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://d/hook"}):
            with patch.object(config, "PUSH_ONLY_ON_BAND_CHANGE", True):
                with self._mock_urlopen():
                    self.assertEqual(notify.push_report("msg", band_change=False), 0)
                    self.assertEqual(notify.push_report("msg", band_change=True), 1)


class TestJobDue(unittest.TestCase):
    """server._job_due — pure scheduler due-logic."""

    def test_fires_within_grace_window_once_per_day(self):
        from datetime import datetime as dt
        import server
        et = dt(2026, 7, 6, 9, 12)          # Monday 09:12 ET
        self.assertTrue(server._job_due("09:00", et, None, True))
        self.assertFalse(server._job_due("09:00", et, "2026-07-06", True))   # fired
        self.assertFalse(server._job_due("09:00", dt(2026, 7, 6, 8, 59), None, True))
        self.assertFalse(server._job_due("09:00", dt(2026, 7, 6, 11, 0), None, True))
        self.assertFalse(server._job_due("09:00", et, None, False))  # holiday/weekend


if __name__ == "__main__":
    unittest.main(verbosity=2)
