# Next-Session Trading Conditions Backtest — Design

Date: 2026-06-12
Status: Approved design, pending spec review
Branch: `feat/conditions-backtest` (stacked on `feat/repositioning-copy-pass`, PR #41)

## Problem

PR #40 falsified the score as a *return* timer, but the product's actual
question — "is today a good day to trade actively?" — was never tested. The
score may predict next-session *trading conditions* (clean trends vs whipsaw)
even though it cannot time index returns. This experiment tests that, with a
pre-registered hypothesis so the result is a verdict, not a fishing trip.

## Pre-registered hypothesis (decided before any data is computed)

**H1:** Next-session range efficiency is higher after top-decile score days
than after bottom-decile score days.

**Verdict rule:** PASS iff the 95% moving-block bootstrap CI (existing
`block_bootstrap_ci`, 21-day blocks, seed 20260611, 2,000 resamples) of
(top-decile mean − bottom-decile mean) range efficiency excludes zero in the
positive direction. Otherwise FAIL. The report prints the verdict either way;
the other three metrics are descriptive context and cannot rescue a FAIL.

## Outcome metrics (SPY, session T+1, daily OHLC)

For a day T scored at the close, the session the score would influence is
T+1. All metrics use SPY's RAW (unadjusted) OHLC for T+1 — same-day ratios
are scale-invariant; the gap metric uses T's raw close and therefore carries
a small dividend bias on ~4 days/year (disclosed in limitations).

| Metric | Formula | Meaning |
|---|---|---|
| Range efficiency | `abs(C − O) / (H − L)` | Trend persistence: 1.0 = clean trend day, ~0 = round-trip chop |
| Range size | `(H − L) / prev_C` | Opportunity magnitude |
| Gap share | `min(1.0, abs(O − prev_C) / (H − L))` | Fraction of movement that happened overnight (untradeable) |
| Trend day | `range efficiency > 0.6` | Binary convenience view of efficiency |

Degenerate handling: if any input is missing or `H == L`, the row's
condition metrics are `None` and excluded from all statistics.

## Changes by stage

### 1. Replay (`backtest.py`) — networked stage stores raw data only

- `_fetch` keeps Yahoo's `open` series (already present in the API response
  under `indicators.quote[0].open`; currently discarded). Cached payloads
  gain an `"open"` key.
- Cache migration: on load, any cached symbol payload missing the `"open"`
  key is refetched automatically (no manual `--refresh` needed). Only SPY's
  opens are consumed, but the fetch change is uniform.
- The replay writes five new CSV columns per scored day T:
  `nd_open, nd_high, nd_low, nd_close` = SPY raw OHLC for trading day T+1
  (empty when T is the last scored day), plus `nd_prev_close` = SPY raw
  close of day T itself, so every row is self-contained for metric
  computation (day T's raw close appears nowhere else in the CSV).

### 2. Pure metrics + statistics (`backtest_stats.py`)

- `BacktestRow` gains five optional fields:
  `nd_open, nd_high, nd_low, nd_close, nd_prev_close: float | None`.
- `condition_metrics(row) -> ConditionMetrics | None` where
  `ConditionMetrics` is a TypedDict `{range_eff, range_pct, gap_share,
  trend_day}`; returns `None` on missing inputs or `H == L`.
- `condition_decile_spread_statistic(metric: str) ->
  Callable[[list[BacktestRow]], float]`: sorts the (re)sample by `total`,
  takes top and bottom deciles (n//10), returns mean(top) − mean(bottom) of
  the named metric over rows with non-None metrics; NaN when a decile has
  no valid rows. **Sign convention: positive = high score better** (flipped
  vs the existing return-based `decile_spread_statistic`; stated in the
  docstring).
- `condition_band_table(rows)` / `condition_decile_table(rows)`: descriptive
  mean metrics per decision band and per score decile (valid-row counts
  included).

### 3. Report (`backtest_report.py`)

- `load_rows` parses the five new columns as optional floats (`None` when
  the column is absent or empty) — old CSVs keep working.
- New section `## Next-Session Trading Conditions`, placed after
  `## Transaction Cost / Slippage Sensitivity` and before
  `## Product Interpretation`. Contents, in order:
  1. One-paragraph explanation of the metrics and the T+1 convention.
  2. **Verdict block** (rendered first among results): the pre-registered
     H1, the spread point estimate, its 95% CI, and `**VERDICT: PASS**` or
     `**VERDICT: FAIL**`.
  3. Band table: metric means × 5 decision bands (+ valid-day counts).
  4. Decile table: metric means × 10 score deciles.
  5. CI table: bootstrap CIs for all four decile spreads; the three
     non-primary rows labeled `(descriptive)`.
- Executive Readout gains one line stating the verdict and the primary
  spread with CI.
- Degradation rules (mirroring the significance section's pattern):
  - Zero rows with non-None condition metrics → section header plus
    `_No next-session OHLC columns in this CSV — re-run `python3
    backtest.py` to populate them._`
  - Tables render whenever at least one valid row exists.
  - The verdict's bootstrap needs ≥ 42 rows (`block_bootstrap_ci`'s
    existing guard); on smaller samples the verdict block prints
    `VERDICT: insufficient sample` instead of PASS/FAIL. Report tests use
    the doubled 60-row fixture (existing precedent) to exercise the real
    verdict path.
- Limitations gains: gap metric uses raw prior close (small dividend bias);
  daily OHLC proxies intraday conditions (no true intraday bars).

### 4. Tests

- `test_backtest_stats.py`: hand-computed fixtures (O=100, H=110, L=98,
  C=109, prevC=100 → range_eff 0.75, range_pct 0.12, gap_share 0.0,
  trend_day True); `H == L` and missing-field rows → None; spread statistic
  sign convention (high-score rows given high efficiency → positive spread);
  NaN when a decile is all-None; determinism via the existing seeded
  bootstrap.
- `test_backtest_report.py`: fixture CSV extended with the five columns;
  assertions for section presence, position (after cost section, before
  Product Interpretation), the verdict line, the `(descriptive)` labels,
  and the graceful-degrade message when columns are absent.
- `make_rows` in `test_backtest_stats.py` gains the five optional kwargs
  (default `None`).

### 5. Execution / regeneration

Implementation ends with: `python3 backtest.py` (networked; auto-refetches
symbols lacking `open`, then full replay — minutes), then
`python3 backtest_report.py`, then committing `docs/backtest-report.md`
with the verdict **whatever it says**, plus a one-line verdict note in
`docs/backtest-methodology.md`'s headline-claim list.

## Out of scope

- QQQ/IWM or any additional symbols.
- True intraday bars or any new data source.
- UI/dashboard changes and README claim changes (those follow the verdict
  in a separate copy change, gated by the claim-hygiene test).
- The vol-target dashboard display (separate spec, next).

## Risks

- Yahoo may return null opens for early-2000s sessions; rows with missing
  inputs degrade to None and drop out of the statistics (counts shown in
  the tables make attrition visible).
- The replay re-run changes `backtest_results.csv` (git-ignored) and the
  committed report; the report's pre-existing numbers must not change
  except the new section and readout line — fwd returns still come from
  adjusted closes. A check in the final task compares the old and new
  strategy tables.
