# Prospective Forecast Log — Predeclared Design

**Status:** Active (EOD track since 2026-07-12, model v6.1)
**Plan tasks:** P3-001, P3-005..P3-013 · **Decision:** D-009 (prospective
evidence outranks retrospective tuning)

Every trading day at the 16:05 ET snapshot, `forecast_log.py` appends one
immutable record of what the model said to `forecasts.jsonl`. Outcomes are
computed later from the next session's OHLC and appended to
`forecast_outcomes.jsonl`. Forecasts are never edited; `--audit` verifies
this with per-record hashes.

The point: the score gets graded by days it had not seen. No retrospective
tuning can touch these numbers.

## Tracks

| Track | Time (ET) | Status |
|---|---|---|
| `eod` | 16:05 close snapshot | **Active** — the concept the 2005–2026 replay tested |
| `premarket` / `1000` / `1200` | — | Not started; separate tracks, never pooled with EOD |

## Predeclared outcome definitions (P3-005..P3-008)

Declared **before** grading began; changing any formula requires a new track
or version — existing outcomes are never recomputed.

Let `C0` = SPY close on the forecast date; `O1/H1/L1/C1` = the next daily
bar's raw (unadjusted) open/high/low/close from Yahoo daily bars.

| Outcome | Formula | Notes |
|---|---|---|
| `next_return_pct` | `C1/C0 − 1` (%) | Close-to-close; direction context, not an alpha claim |
| `range_size_pct` | `(H1 − L1)/C0` (%) | Descriptive session size |
| `range_efficiency` | `\|C1 − O1\|/(H1 − L1)` | 1 ≈ clean trend day, ~0 ≈ round-trip chop; `null` when `H1 = L1` |
| `favorable_excursion_pct` | `H1/C0 − 1` (%) | Best case from the forecast reference |
| `adverse_excursion_pct` | `L1/C0 − 1` (%) | Worst case from the forecast reference |
| `large_move` | `\|next_return_pct\| ≥ 1.5%` | Event flag |

**Missing-data rule:** a forecast stays ungraded until its next daily bar
exists (weekends/holidays wait for the next trading day). Grading runs at
the following EOD job and via `python3 forecast_log.py --grade`.

**Grading delay:** outcomes are computed no earlier than one session after
the forecast; vendor bar revisions after grading are not re-applied.

## Sample-size minimum (P3-009)

No rolling metric is displayed for a track with fewer than
**60 graded forecasts** (`MIN_SAMPLE_FOR_DISPLAY`). Early aggregate numbers
are noise theater; the raw records are still available for export.

## Storage & persistence (P3-010, Q-006)

Records are local JSONL files next to the code, git-ignored. **The public
Render demo's filesystem is ephemeral** — records vanish on spin-down, so
`/health` reports `forecast_log.persistent: false` there. A real archive
requires running locally (launchd/cron) or attaching durable storage.

## Integrity (P3-011, P3-012)

- One record per `(model_version, track, date)`; re-runs are no-ops.
- Days with invalid data quality are not recorded — a disabled reading is
  not a forecast.
- `input_manifest_hash` = SHA-256 over the canonical record body;
  `python3 forecast_log.py --audit` reports tampered records, duplicates,
  and calendar gaps (missed observations), and exits non-zero on integrity
  failures.
- Model transitions are visible per record (`model_version`,
  `engine_commit`); different versions are never pooled silently (P3-017).

## What this is not

Not a trading system, not a performance claim, and not a leaderboard. It is
the mechanism by which the dashboard earns — or fails to earn — any future
claim, prospectively.
