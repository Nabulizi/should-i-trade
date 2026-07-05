# Daily Push + Day-over-Day Delta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push a one-message market-conditions report to Telegram/Discord every trading morning, and show "since yesterday" score/pillar deltas in the dashboard, both fed by a new one-snapshot-per-trading-day store.

**Architecture:** A new `daily_history.py` module owns the per-day snapshot store (`daily_history.json`). A new `notify.py` module builds the Markdown report (pure function) and sends it via stdlib `urllib` to Telegram and/or Discord. A daemon scheduler thread in `server.py` fires two ET-time jobs (16:05 EOD snapshot, 09:00 push) on trading days, using the existing `market_state()` for holiday/weekend detection. `/api/dashboard` gains a nullable `yesterday` field rendered by `app.js` as a "Since yesterday" strip (v6 UI only — classic.html has its own renderer).

**Tech Stack:** Python 3.10+ stdlib only (json, urllib.request, threading, datetime), unittest + unittest.mock, vanilla JS + Vitest.

## Global Constraints

- Stdlib only — no new pip dependencies (spec: "stdlib only, no required API keys").
- All tests fully offline; `urllib.request.urlopen` always mocked.
- Secrets only in git-ignored `config_local.py` or env vars; env var wins (matches `GEMINI_API_KEY` pattern).
- Push silently disabled when no channel configured; default installs see zero behavior change.
- Atomic tempfile writes for `daily_history.json` (same pattern as `history.json`).
- Scheduler failures log and never crash the thread or server.
- Config defaults: `PUSH_TIME_ET="09:00"`, `EOD_SNAPSHOT_TIME_ET="16:05"`, `PUSH_ONLY_ON_BAND_CHANGE=False`, `DAILY_HISTORY_MAXLEN=90`, `DASHBOARD_URL="http://localhost:8765"`.

---

### Task 1: `et_now()` helper in data.py

**Files:**
- Modify: `data.py` (near `market_state`, line ~676)
- Test: `test_data.py` (append)

**Interfaces:**
- Produces: `data.et_now() -> datetime` — current wall-clock time in US/Eastern as a naive datetime. `market_state()` refactored to use it (no behavior change).

- [ ] **Step 1: Write failing tests** (append to `test_data.py`)

```python
class TestEtNow(unittest.TestCase):
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
```

- [ ] **Step 2: Run** `python3 test_data.py` — expect FAIL (`data has no attribute et_now`).

- [ ] **Step 3: Implement** in `data.py`, directly above `market_state()`:

```python
def et_now() -> datetime:
    """Current US/Eastern wall-clock time as a naive datetime (DST-aware)."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    offset = -4 if _is_dst_et(now_utc) else -5
    return now_utc + timedelta(hours=offset)
```

Refactor `market_state()` first three lines to `et = et_now()` (delete its own now_utc/offset lines).

- [ ] **Step 4: Run** `python3 test_data.py` — expect all pass (existing market_state tests prove no regression).

- [ ] **Step 5: Commit** `feat(data): add et_now() helper, reuse in market_state`

---

### Task 2: daily_history.py store + config

**Files:**
- Create: `daily_history.py`
- Modify: `config.py` (append before Local Overrides block), `.gitignore` (add `daily_history.json`)
- Test: create `test_daily_history.py`

**Interfaces:**
- Consumes: `config.DAILY_HISTORY_MAXLEN`.
- Produces:
  - `load_daily_history(path=DAILY_HISTORY_FILE) -> list[dict]`
  - `record_daily_snapshot(data: dict, et_date: str, path=...) -> dict | None` — builds `{"date", "total", "decision", "pillars": {five names: int}}` from a dashboard payload; skips (returns None) when `data_quality.valid` is False; replaces same-date entry; caps at maxlen; atomic write.
  - `yesterday_snapshot(today_date: str, path=...) -> dict | None` — newest entry with `date < today_date`.
  - Module constant `DAILY_HISTORY_FILE` (abs path next to script).

- [ ] **Step 1: config.py** — append:

```python
# ── Daily Push Report & Day-over-Day Delta ───────────────────────────────────

DAILY_HISTORY_MAXLEN: int = 90
"""Trading-day close snapshots kept in daily_history.json (~4.5 months)."""

EOD_SNAPSHOT_TIME_ET: str = "16:05"
"""ET wall-clock time the end-of-day snapshot job runs (trading days only)."""

PUSH_TIME_ET: str = "09:00"
"""ET wall-clock time the morning push report is sent (trading days only)."""

PUSH_ONLY_ON_BAND_CHANGE: bool = False
"""When True, the morning push is sent only if the posture band changed
   vs the previous close (low-noise mode)."""

DASHBOARD_URL: str = "http://localhost:8765"
"""Link shown in the push message footer."""

TELEGRAM_BOT_TOKEN: str = ""
"""Telegram bot token from @BotFather. ⚠ Set in config_local.py or env var."""

TELEGRAM_CHAT_ID: str = ""
"""Telegram chat ID the report is sent to. ⚠ Set in config_local.py or env."""

DISCORD_WEBHOOK_URL: str = ""
"""Discord channel webhook URL. ⚠ Set in config_local.py or env var."""
```

- [ ] **Step 2: Write failing tests** — `test_daily_history.py` (unittest style matching test_data.py; use `tempfile.TemporaryDirectory` for path):

```python
"""test_daily_history.py — offline tests for the per-trading-day snapshot store."""
from __future__ import annotations
import json, os, sys, tempfile, unittest

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
        self.assertEqual(snap["pillars"]["trend"], 72)
        self.assertEqual(load_daily_history(self.path), [snap])

    def test_same_date_replaces(self):
        record_daily_snapshot(_payload(total=70), "2026-07-02", path=self.path)
        record_daily_snapshot(_payload(total=75), "2026-07-02", path=self.path)
        hist = load_daily_history(self.path)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["total"], 75)

    def test_invalid_data_skipped(self):
        self.assertIsNone(record_daily_snapshot(_payload(valid=False), "2026-07-02", path=self.path))
        self.assertEqual(load_daily_history(self.path), [])

    def test_maxlen_cap(self):
        for i in range(daily_history.DAILY_HISTORY_MAXLEN + 5):
            record_daily_snapshot(_payload(), f"2026-01-{i:03d}", path=self.path)
        self.assertEqual(len(load_daily_history(self.path)), daily_history.DAILY_HISTORY_MAXLEN)

    def test_yesterday_snapshot_picks_latest_before_today(self):
        record_daily_snapshot(_payload(total=60), "2026-07-01", path=self.path)
        record_daily_snapshot(_payload(total=68), "2026-07-02", path=self.path)
        record_daily_snapshot(_payload(total=72), "2026-07-03", path=self.path)
        y = yesterday_snapshot("2026-07-03", path=self.path)
        self.assertEqual(y["total"], 68)
        self.assertIsNone(yesterday_snapshot("2026-07-01", path=self.path))

    def test_corrupt_file_recovers_empty(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(load_daily_history(self.path), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3: Run** `python3 test_daily_history.py` — FAIL (no module).

- [ ] **Step 4: Implement `daily_history.py`:**

```python
"""daily_history.py — one end-of-day snapshot per trading day.

Feeds the "Since yesterday" dashboard strip and the morning push report.
Storage: daily_history.json (git-ignored, auto-created, atomic writes),
newest entry last, capped at config.DAILY_HISTORY_MAXLEN.
"""
from __future__ import annotations
import json, logging, os, tempfile

from config import DAILY_HISTORY_MAXLEN

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_HISTORY_FILE = os.path.join(SCRIPT_DIR, "daily_history.json")

_PILLARS = ("volatility", "trend", "breadth", "momentum", "macro")


def load_daily_history(path: str = DAILY_HISTORY_FILE) -> list[dict]:
    """Load snapshots from disk; corrupt or missing file yields []. """
    try:
        with open(path, encoding="utf-8") as f:
            hist = json.load(f)
        return hist if isinstance(hist, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("daily_history.json corrupt (%s) — starting fresh.", exc)
        return []


def _save(history: list[dict], path: str) -> None:
    dir_ = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".daily_tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(history, f)
        os.replace(tmp_path, path)
    except OSError:
        logger.exception("Failed to save daily_history.json")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def record_daily_snapshot(data: dict, et_date: str,
                          path: str = DAILY_HISTORY_FILE) -> dict | None:
    """Append (or same-date replace) a close snapshot built from a dashboard payload.

    Returns the snapshot, or None when data quality is invalid (no fake closes).
    """
    if not data.get("data_quality", {}).get("valid", True):
        logger.warning("EOD snapshot skipped for %s — data quality invalid.", et_date)
        return None
    snapshot = {
        "date": et_date,
        "total": data["total_score"],
        "decision": data.get("decision", ""),
        "pillars": {p: data["pillars"][p]["score"] for p in _PILLARS},
    }
    history = [s for s in load_daily_history(path) if s.get("date") != et_date]
    history.append(snapshot)
    history.sort(key=lambda s: s.get("date", ""))
    _save(history[-DAILY_HISTORY_MAXLEN:], path)
    return snapshot


def yesterday_snapshot(today_date: str,
                       path: str = DAILY_HISTORY_FILE) -> dict | None:
    """Newest snapshot strictly before today_date (ISO yyyy-mm-dd), else None."""
    prior = [s for s in load_daily_history(path) if s.get("date", "") < today_date]
    return prior[-1] if prior else None
```

- [ ] **Step 5: Run** `python3 test_daily_history.py` — all pass. Add `daily_history.json` to `.gitignore`.

- [ ] **Step 6: Commit** `feat: daily close-snapshot store (daily_history.py) + config keys`

---

### Task 3: notify.py — report builder (pure)

**Files:**
- Create: `notify.py`
- Test: create `test_notify.py`

**Interfaces:**
- Consumes: `config.DASHBOARD_URL`; dashboard payload dict; snapshot dict from Task 2.
- Produces:
  - `build_report(data: dict, yesterday: dict | None) -> str` — Markdown message.
  - `_fmt_delta(cur: int, prev: int | None) -> str` — `"▲ +4"` / `"▼ −3"` / `"—"` / `""` (prev None).
  - `band_changed(data: dict, yesterday: dict | None) -> bool`.

- [ ] **Step 1: Write failing tests** — `test_notify.py`:

```python
"""test_notify.py — offline tests for the morning push report."""
from __future__ import annotations
import os, sys, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
        "econ_events": [], "fomc": {"days_until": 25, "date_pretty": "Jul 29"},
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


class TestBuildReport(unittest.TestCase):
    def test_full_report_contains_score_delta_bands_pillars(self):
        text = build_report(_payload(), _yesterday())
        self.assertIn("72", text)
        self.assertIn("▲ +4", text)
        self.assertIn("CONSTRUCTIVE", text)
        self.assertIn("SELECTIVE → CONSTRUCTIVE", text)
        self.assertIn("Trend 72 (▲ +3)", text)
        self.assertIn("http://localhost:8765", text)

    def test_no_yesterday_omits_deltas_and_transition(self):
        text = build_report(_payload(), None)
        self.assertNotIn("→", text)
        self.assertNotIn("▲", text)
        self.assertIn("72", text)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run** `python3 test_notify.py` — FAIL (no module).

- [ ] **Step 3: Implement** `notify.py` (builder half):

```python
"""notify.py — morning push report for the Daily Push feature.

Builds a one-message Markdown conditions report and sends it to any
configured channel (Telegram bot API, Discord webhook). Stdlib only.
Run standalone to test:  python3 notify.py
"""
from __future__ import annotations
import json, logging, os, urllib.request

import config

logger = logging.getLogger(__name__)

_PILLAR_ORDER = ("trend", "breadth", "momentum", "volatility", "macro")
_EVENT_WINDOW_DAYS = 3


def _fmt_delta(cur: int, prev: int | None) -> str:
    if prev is None:
        return ""
    d = cur - prev
    if d > 0:
        return f"▲ +{d}"
    if d < 0:
        return f"▼ {d}"
    return "—"


def band_changed(data: dict, yesterday: dict | None) -> bool:
    return bool(yesterday) and data.get("decision") != yesterday.get("decision")


def build_report(data: dict, yesterday: dict | None) -> str:
    """Pure Markdown report: score+delta, posture, pillars, quality, events."""
    prev_total = yesterday["total"] if yesterday else None
    date = (data.get("market_state") or {}).get("et_date", "")
    lines = [f"*Should I Trade? — {date}*"]

    delta = _fmt_delta(data["total_score"], prev_total)
    delta_part = f" ({delta} vs prev close)" if delta else ""
    lines.append(f"*Score {data['total_score']}*{delta_part} — {data.get('decision', '')}")

    if band_changed(data, yesterday):
        lines.append(f"Posture change: {yesterday['decision']} → {data['decision']}")

    pillar_bits = []
    for p in _PILLAR_ORDER:
        score = data["pillars"][p]["score"]
        prev = yesterday["pillars"].get(p) if yesterday else None
        d = _fmt_delta(score, prev)
        pillar_bits.append(f"{p.capitalize()} {score}" + (f" ({d})" if d else ""))
    lines.append(" · ".join(pillar_bits))

    dq = data.get("data_quality", {})
    if not dq.get("valid", True):
        lines.append(f"⚠ Data degraded: {dq.get('message', 'live feeds unavailable')}")

    events = [f"{e['name']} {e['date_pretty']} ({e['days_until']}d)"
              for e in data.get("econ_events", [])
              if e.get("days_until", 99) <= _EVENT_WINDOW_DAYS]
    fomc = data.get("fomc") or {}
    if fomc.get("days_until") is not None and fomc["days_until"] <= _EVENT_WINDOW_DAYS:
        events.append(f"FOMC {fomc.get('date_pretty', '')} ({fomc['days_until']}d)")
    if events:
        lines.append("Events: " + " · ".join(events))

    lines.append(config.DASHBOARD_URL)
    return "\n".join(lines)
```

(Payload key check during implementation: the dashboard payload's econ/FOMC keys are confirmed from `scoring.compute_dashboard` — if they differ from `econ_events`/`fomc`, use the real names in both code and tests.)

- [ ] **Step 4: Run** `python3 test_notify.py` — pass.

- [ ] **Step 5: Commit** `feat(notify): pure Markdown report builder with day-over-day deltas`

---

### Task 4: notify.py — senders + push_report

**Files:**
- Modify: `notify.py` (append), `test_notify.py` (append)

**Interfaces:**
- Consumes: config keys `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`, `PUSH_ONLY_ON_BAND_CHANGE` (env vars override).
- Produces:
  - `_channel(name: str) -> str` — env-first config lookup.
  - `send_telegram(text: str) -> bool`, `send_discord(text: str) -> bool`
  - `push_report(text: str, *, band_change: bool = True) -> int` — number of channels that accepted; honors `PUSH_ONLY_ON_BAND_CHANGE`; returns 0 silently when nothing configured.

- [ ] **Step 1: Append failing tests** to `test_notify.py`:

```python
class TestSenders(unittest.TestCase):
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

    def test_failure_logged_not_raised_retries_once(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://d/hook"}):
            with patch("notify.urllib.request.urlopen", side_effect=OSError("boom")) as m:
                self.assertFalse(notify.send_discord("hello"))
        self.assertEqual(m.call_count, 2)   # one retry

    def test_push_report_counts_configured_channels_only(self):
        env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c",
               "DISCORD_WEBHOOK_URL": ""}
        with patch.dict(os.environ, env):
            with self._mock_urlopen():
                self.assertEqual(notify.push_report("msg"), 1)

    def test_push_report_zero_when_unconfigured(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "",
                                     "DISCORD_WEBHOOK_URL": ""}):
            self.assertEqual(notify.push_report("msg"), 0)

    def test_band_change_gate(self):
        env = {"DISCORD_WEBHOOK_URL": "https://d/hook"}
        with patch.dict(os.environ, env):
            with patch.object(config, "PUSH_ONLY_ON_BAND_CHANGE", True):
                with self._mock_urlopen():
                    self.assertEqual(notify.push_report("msg", band_change=False), 0)
                    self.assertEqual(notify.push_report("msg", band_change=True), 1)
```

Note: tests must also `import json` and `import config` at top of file (add to imports).

- [ ] **Step 2: Run** — FAIL (missing functions).

- [ ] **Step 3: Implement** (append to `notify.py`):

```python
_HTTP_TIMEOUT = 10


def _channel(name: str) -> str:
    """Config lookup with env-var priority (matches GEMINI_API_KEY pattern)."""
    return os.environ.get(name) or getattr(config, name, "") or ""


def _post_json(url: str, payload: dict, label: str) -> bool:
    """POST JSON with one retry. Failures are logged, never raised."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    return True
                logger.warning("%s push HTTP %s (attempt %d)", label, resp.status, attempt)
        except OSError as exc:
            logger.warning("%s push failed (attempt %d): %s", label, attempt, exc)
    return False


def send_telegram(text: str) -> bool:
    token, chat_id = _channel("TELEGRAM_BOT_TOKEN"), _channel("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False
    return _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        "telegram")


def send_discord(text: str) -> bool:
    url = _channel("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    return _post_json(url, {"content": text}, "discord")


def channels_configured() -> bool:
    return bool((_channel("TELEGRAM_BOT_TOKEN") and _channel("TELEGRAM_CHAT_ID"))
                or _channel("DISCORD_WEBHOOK_URL"))


def push_report(text: str, *, band_change: bool = True) -> int:
    """Send to every configured channel; returns how many accepted."""
    if not channels_configured():
        return 0
    if config.PUSH_ONLY_ON_BAND_CHANGE and not band_change:
        logger.info("Push skipped: posture band unchanged (low-noise mode).")
        return 0
    sent = 0
    if _channel("TELEGRAM_BOT_TOKEN") and _channel("TELEGRAM_CHAT_ID"):
        sent += send_telegram(text)
    if _channel("DISCORD_WEBHOOK_URL"):
        sent += send_discord(text)
    return sent
```

- [ ] **Step 4: Run** `python3 test_notify.py` — pass.

- [ ] **Step 5: Commit** `feat(notify): Telegram/Discord senders + push_report gate`

---

### Task 5: Scheduler thread + yesterday field in server.py

**Files:**
- Modify: `server.py` (imports; `_do_recompute`; new scheduler section; `main()`)
- Test: append to `test_notify.py` (scheduler helpers are pure) + extend `test_contracts.py` is NOT needed (yesterday is server-attached, not part of compute_dashboard); instead add assertions to `test_smoke.py` if it exercises `_do_recompute`, else unit-test `_job_due` only.

**Interfaces:**
- Consumes: `data.et_now()`, `data.market_state()`, `daily_history.*`, `notify.*`, config `EOD_SNAPSHOT_TIME_ET`, `PUSH_TIME_ET`.
- Produces:
  - `server._job_due(job_hhmm: str, et, last_fired_date: str | None, tradable: bool, grace_min: int = 90) -> bool` — pure, testable.
  - `/api/dashboard` payload gains `"yesterday": dict | None`.

- [ ] **Step 1: Append failing tests** to `test_notify.py`:

```python
from datetime import datetime as _dt

class TestJobDue(unittest.TestCase):
    def test_fires_within_grace_window_once_per_day(self):
        import server
        et = _dt(2026, 7, 6, 9, 12)          # Monday 09:12 ET
        self.assertTrue(server._job_due("09:00", et, None, True))
        self.assertFalse(server._job_due("09:00", et, "2026-07-06", True))   # already fired
        self.assertFalse(server._job_due("09:00", _dt(2026, 7, 6, 8, 59), None, True))  # early
        self.assertFalse(server._job_due("09:00", _dt(2026, 7, 6, 11, 0), None, True))  # past grace
        self.assertFalse(server._job_due("09:00", et, None, False))          # holiday/weekend
```

- [ ] **Step 2: Run** — FAIL (`_job_due` missing).

- [ ] **Step 3: Implement in server.py.**

Imports: add `from daily_history import record_daily_snapshot, yesterday_snapshot`, `from data import et_now, market_state`, `import notify`, and config keys `EOD_SNAPSHOT_TIME_ET, PUSH_TIME_ET`.

In `_do_recompute`, right after `data["stale"] = False`, attach:

```python
    data["yesterday"] = yesterday_snapshot(et_now().date().isoformat())
```

New section (above `main()`):

```python
# ─── daily scheduler (EOD snapshot + morning push) ────────────────────────

def _job_due(job_hhmm: str, et, last_fired_date: str | None,
             tradable: bool, grace_min: int = 90) -> bool:
    """True when ET clock is within [job_time, job_time+grace) today,
    the market traded today, and the job hasn't fired today yet."""
    if not tradable or last_fired_date == et.date().isoformat():
        return False
    jh, jm = map(int, job_hhmm.split(":"))
    start = jh * 60 + jm
    now = et.hour * 60 + et.minute
    return start <= now < start + grace_min

def _fresh_dashboard() -> dict:
    with _COMPUTE_LOCK:
        return _do_recompute()

def _run_due_jobs(last_fired: dict) -> None:
    et = et_now()
    today = et.date().isoformat()
    tradable = market_state()["state"] not in ("weekend", "closed")

    if _job_due(EOD_SNAPSHOT_TIME_ET, et, last_fired["eod"], tradable):
        last_fired["eod"] = today
        record_daily_snapshot(_fresh_dashboard(), today)
        logger.info("EOD snapshot recorded for %s", today)

    if notify.channels_configured() and \
            _job_due(PUSH_TIME_ET, et, last_fired["push"], tradable):
        last_fired["push"] = today
        data = _fresh_dashboard()
        yday = yesterday_snapshot(today)
        sent = notify.push_report(notify.build_report(data, yday),
                                  band_change=notify.band_changed(data, yday))
        logger.info("Morning push: %d channel(s) delivered", sent)

def _scheduler_loop() -> None:
    last_fired = {"eod": None, "push": None}
    while True:
        try:
            _run_due_jobs(last_fired)
        except Exception:
            logger.exception("Scheduler job failed — will retry next cycle")
        time.sleep(30)
```

In `main()`, after `_load_history()`:

```python
    threading.Thread(target=_scheduler_loop, daemon=True,
                     name="daily-scheduler").start()
```

- [ ] **Step 4: Run** `python3 test_notify.py && python3 -m unittest discover -q` — all pass.

- [ ] **Step 5: Commit** `feat(server): daily scheduler (EOD snapshot + morning push), yesterday in payload`

---

### Task 6: "Since yesterday" strip in the v6 UI

**Files:**
- Modify: `static/app.js` (new exported `renderYesterdayStrip(d)`, called where `renderHero` output lands), `static/app.css` (strip styling), `should-i-trade-v6.html` (container element if the hero doesn't allow injection)
- Test: append to `static/app.test.js`

**Interfaces:**
- Consumes: dashboard payload `yesterday` field (Task 5 shape).
- Produces: `renderYesterdayStrip(d) -> string` (HTML or `""`), exported for tests.

- [ ] **Step 1: Append failing tests** to `static/app.test.js`:

```js
import { renderYesterdayStrip } from './app.js';

describe('renderYesterdayStrip', () => {
  const d = {
    total_score: 72, decision: 'CONSTRUCTIVE',
    pillars: {
      volatility: { score: 88 }, trend: { score: 72 }, breadth: { score: 88 },
      momentum: { score: 50 }, macro: { score: 61 },
    },
    yesterday: {
      date: '2026-07-03', total: 68, decision: 'SELECTIVE',
      pillars: { volatility: 88, trend: 69, breadth: 82, momentum: 52, macro: 61 },
    },
  };

  it('renders total delta, pillar deltas, and band transition', () => {
    const html = renderYesterdayStrip(d);
    expect(html).toContain('+4');
    expect(html).toContain('SELECTIVE');
    expect(html).toContain('CONSTRUCTIVE');
    expect(html).toContain('Trend');
  });

  it('returns empty string when no yesterday snapshot', () => {
    expect(renderYesterdayStrip({ ...d, yesterday: null })).toBe('');
  });

  it('omits the transition line when the band is unchanged', () => {
    const same = { ...d, yesterday: { ...d.yesterday, decision: 'CONSTRUCTIVE' } };
    expect(renderYesterdayStrip(same)).not.toContain('→');
  });
});
```

- [ ] **Step 2: Run** `npm test` — FAIL (not exported).

- [ ] **Step 3: Implement** in `static/app.js` (near `renderHero`; exact insertion point + markup adapted to the current hero structure during implementation — reuse existing utility classes / design tokens from the calm UI):

```js
function renderYesterdayStrip(d) {
  const y = d.yesterday;
  if (!y) return '';
  const delta = (cur, prev) => {
    const df = cur - prev;
    if (df > 0) return `<span class="delta up">▲ +${df}</span>`;
    if (df < 0) return `<span class="delta down">▼ ${df}</span>`;
    return `<span class="delta flat">—</span>`;
  };
  const pillars = ['trend', 'breadth', 'momentum', 'volatility', 'macro']
    .map((p) => `<span class="y-pillar">${p[0].toUpperCase() + p.slice(1)}
      ${delta(d.pillars[p].score, y.pillars[p])}</span>`)
    .join('');
  const band = y.decision !== d.decision
    ? `<span class="y-band">${y.decision} → ${d.decision}</span>` : '';
  return `<div class="yesterday-strip" role="note" aria-label="Change since previous close">
    <span class="y-label">Since yesterday (${y.date})</span>
    <span class="y-total">${delta(d.total_score, y.total)}</span>
    ${band}${pillars}</div>`;
}
```

Call it from the dashboard render path (where `renderHero(d)` is invoked) and inject below the hero; add to the export list at the bottom of app.js. CSS in `app.css`: one `.yesterday-strip` rule block using existing color tokens (muted foreground, green/red delta colors already defined for `chgStr` outputs).

- [ ] **Step 4: Run** `npm test && npm run lint` — pass.

- [ ] **Step 5: Commit** `feat(ui): "Since yesterday" delta strip in v6 dashboard`

---

### Task 7: Standalone entry point + docs + full verification

**Files:**
- Modify: `notify.py` (main guard), `README.md` (new "Daily Push Report" section under Features/Configuration), `CLAUDE.md` (module table + architecture note)

**Interfaces:**
- Consumes: everything above.
- Produces: `python3 notify.py` sends one report immediately (manual test / external schedulers).

- [ ] **Step 1: Append to notify.py:**

```python
def send_now() -> int:
    """Compute a fresh dashboard and push the report once. Returns channels sent."""
    from scoring import compute_dashboard
    from daily_history import yesterday_snapshot
    from data import et_now
    data = compute_dashboard()
    yday = yesterday_snapshot(et_now().date().isoformat())
    text = build_report(data, yday)
    print(text)
    if not channels_configured():
        print("\n(no channel configured — set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID "
              "or DISCORD_WEBHOOK_URL in config_local.py)")
        return 0
    return push_report(text, band_change=band_changed(data, yday))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sent = send_now()
    print(f"\nDelivered to {sent} channel(s).")
```

- [ ] **Step 2: README** — add a "Daily Push Report" section: what it is, 2-minute Telegram setup (@BotFather → token; message the bot; get chat id via `getUpdates`), Discord webhook setup, config keys table, `python3 notify.py` manual test, `PUSH_ONLY_ON_BAND_CHANGE` low-noise mode, note that the public Render demo never pushes (no secrets). Update Features table (+ Daily Push row, + Since-yesterday delta row) and Project Structure tree (+ notify.py, daily_history.py). CLAUDE.md: add both modules to the key-modules table.

- [ ] **Step 3: Full verification:**

```bash
python3 -m py_compile server.py notify.py daily_history.py data.py
python3 -m unittest discover -q && python3 test_fixes.py
npm test && npm run lint
python3 notify.py        # prints report; "(no channel configured …)" locally
```

All green; manual `notify.py` run prints a plausible report.

- [ ] **Step 4: Commit** `feat: standalone push entry point + docs for daily push & delta`
