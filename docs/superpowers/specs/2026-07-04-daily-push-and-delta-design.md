# Daily Push Notification + Day-over-Day Delta — Design

**Date:** 2026-07-04
**Status:** Approved direction from user ("start with #1 and #2"); channel/trigger
defaults chosen by Claude (user AFK), swappable via config.

## Purpose

should-i-trade is a *pre-session* market quality gauge, but it only helps if the
user remembers to open the dashboard. Two features close that gap:

1. **Daily push** — every trading morning, send a one-message conditions report
   (score, posture, pillar deltas, econ events) to Telegram and/or Discord.
2. **Day-over-day delta** — persist one end-of-day snapshot per trading day and
   surface "since yesterday" changes both in the push message and as a strip in
   the dashboard UI.

Both features share the same new data artifact: the daily close snapshot.

Inspiration: `daily_stock_analysis` (ZhuLinsen) push-report model and its
history-comparison service — adapted to this project's constraints: stdlib
only, no required API keys, market-level not per-stock.

## Non-goals

- No per-stock analysis, no LLM content in the push (rule-based text only).
- No email/SMTP channel (worst rendering, most friction). Can be added later.
- No GitHub Actions scheduling in this iteration; `notify.py` runs standalone
  so external schedulers (cron/launchd/Actions) remain possible.
- No change to the existing intraday sparkline history (`history.json`).

## Components

### 1. `daily_history.json` + persistence (in `server.py`)

- One JSON array, newest last, entries:
  `{"date": "2026-07-02", "total": 72, "decision": "CONSTRUCTIVE",
    "pillars": {"volatility": 88, "trend": 72, "breadth": 88,
                "momentum": 50, "macro": 61}}`
- Written at the 16:05 ET job on trading days, only when
  `data_quality.valid` is true. Atomic tempfile write, same pattern as
  `history.json`. Capped at `DAILY_HISTORY_MAXLEN` (default 90) entries.
- Git-ignored, auto-created, corrupt file ⇒ warn and start fresh (same
  semantics as `history.json`).
- Idempotent per date: re-running the job on the same date replaces that
  date's entry instead of appending a duplicate.

### 2. Scheduler thread (in `server.py`)

- One daemon thread started from `main()` alongside existing startup.
- Two daily jobs, times in ET (reusing the DST math in `data.py`):
  - `EOD_SNAPSHOT_TIME_ET` (default "16:05") → recompute dashboard → append
    daily snapshot.
  - `PUSH_TIME_ET` (default "09:00") → recompute dashboard → build report →
    send via configured channels.
- Both jobs skip weekends/NYSE holidays via existing `market_state()` /
  `_nyse_holidays()`.
- Loop: sleep in ≤60 s increments, fire when the ET wall-clock crosses a job
  time, guard against double-fire with a "last fired date" per job.
- Failures log and never crash the thread; next day retries naturally.
- The scheduler only starts when it has something to do: EOD job always runs
  (feeds the UI delta); the push job is skipped when no channel is configured.

### 3. `notify.py` (new module)

- `build_report(data: dict, yesterday: dict | None) -> str` — pure function,
  Markdown message:
  - Header: date, score with delta vs yesterday's close (e.g. `72 (▲ +4)`),
    posture badge, band transition line when the band changed.
  - Five pillar lines with per-pillar deltas.
  - Data-quality warning line when `data_quality.valid` is false (message
    still sent, clearly flagged as degraded — mirrors the dashboard banner).
  - Upcoming econ/FOMC events from existing `econ_proximity()` /
    `fomc_proximity()` (next ~3 days only).
  - Footer: dashboard URL.
- `send_telegram(text)` / `send_discord(text)` — stdlib `urllib.request`
  POSTs; Telegram uses bot API `sendMessage` (Markdown), Discord uses webhook
  `content`. 10 s timeout, one retry, errors logged not raised.
- `push_report(data, yesterday)` — sends to every configured channel;
  honors `PUSH_ONLY_ON_BAND_CHANGE`.
- `python3 notify.py` (main guard) — computes a fresh dashboard directly
  (no server needed), loads `daily_history.json`, builds and sends the
  report once. Used for manual testing and external schedulers.

### 4. Dashboard delta ("Since yesterday")

- `server.py` attaches `yesterday` to the `/api/dashboard` payload: the most
  recent daily snapshot whose date < today (ET), else `null`.
- `static/app.js` renders a "Since yesterday" strip when present: total
  delta, per-pillar deltas (▲/▼/—), and posture-band transition when it
  changed. Hidden when `yesterday` is null. Styling follows the current UI
  version's design language; the classic UI gets the same data (implement in
  whichever shells share `app.js`; if `/classic` uses a separate renderer,
  new-UI-only is acceptable for this iteration).
- Delta computation happens client-side from `yesterday` + current payload
  (keeps the payload additive and backward-compatible).

### 5. Config

`config.py` (defaults, documented):
```python
PUSH_TIME_ET = "09:00"
EOD_SNAPSHOT_TIME_ET = "16:05"
PUSH_ONLY_ON_BAND_CHANGE = False
DAILY_HISTORY_MAXLEN = 90
TELEGRAM_BOT_TOKEN = ""   # set in config_local.py
TELEGRAM_CHAT_ID = ""     # set in config_local.py
DISCORD_WEBHOOK_URL = ""  # set in config_local.py
DASHBOARD_URL = "http://localhost:8765"  # used in the push footer
```
Secrets live in git-ignored `config_local.py` (existing mechanism); env vars
`TELEGRAM_BOT_TOKEN` etc. override, matching the `GEMINI_API_KEY` precedence
pattern.

Render note: the public demo has no `config_local.py`, so its scheduler runs
only the EOD job and never pushes. No special guard needed.

## Error handling

- Push failures: log at WARNING, never crash the scheduler or server.
- Missing/corrupt `daily_history.json`: warn, treat as empty.
- Invalid data at EOD time: skip the snapshot (no fake closes); the UI strip
  and next morning's delta simply show "no comparison available".
- Invalid data at push time: still push, flagged degraded, delta suppressed.

## Testing (`test_notify.py` + additions)

All offline, mocked `urllib`:
- `build_report`: full message with deltas; band-change line; no-yesterday
  case; degraded-data case; econ-event inclusion window.
- Delta/band math: same band, band up, band down.
- Senders: correct URL/body for Telegram and Discord from mocked config;
  failure → logged, not raised; retry once.
- Scheduler: next-fire logic (before/after job time, weekend/holiday skip,
  no double fire same date) — extracted as a pure helper so it's testable
  without threads.
- Daily history: append, same-date replace, cap at maxlen, corrupt-file
  recovery. Contract test: `/api/dashboard` payload includes `yesterday`
  key (nullable) — extend `test_contracts.py`.
- JS: strip rendering helper unit test in `static/app.test.js` (delta
  arrows, hidden when no yesterday).

## Rollout

Feature branch `feature/daily-push-delta`; README section ("Daily Push
Report") + CLAUDE.md updates in the same branch; no migration steps — new
files auto-create.
