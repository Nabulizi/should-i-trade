# Backtest Robustness Analytics — Design

Date: 2026-06-11
Status: Approved approach (Approach B), pending spec review

## Problem

The current backtest report (`docs/backtest-report.md`) shows the Market Quality
Score timing rule losing to its matched constant-exposure benchmark on return
and (in the validation window) on Sharpe, winning only on max drawdown. Four
robustness questions remain open before any product claim or repositioning
decision:

1. **Vol-targeting baseline** — does the 5-pillar score beat a trivial
   volatility dial at the same risk budget? If not, the pillar machinery adds
   nothing over one volatility line.
2. **Year-by-year table** — is the drawdown benefit spread across years, or
   concentrated in 2-3 crisis episodes (2008, 2020, 2022)?
3. **Bootstrap confidence intervals** — are the negative ICs and the decile-1
   contrarian edge statistically distinguishable from zero, given overlapping
   5-day returns?
4. **Transaction costs** — how much worse does the timing rule get once each
   exposure flip pays a spread?

Product repositioning (renaming the score, regime language, dropping the 70
threshold) is **out of scope** — it gets its own spec after this evidence
exists.

## Architecture

New module `backtest_stats.py` holds the four analytics as pure, deterministic,
stdlib-only functions. `backtest_report.py` imports them and renders new
markdown sections. No changes to `backtest.py` or `backtest_results.csv` — all
inputs derive from the existing CSV columns (`date`, `total`, `decision`,
`fwd1`, `fwd5`).

```
backtest_results.csv
   └─ backtest_report.load_rows()  →  list[BacktestRow]
         ├─ backtest_stats.vol_target_strategy(rows, match_exposure_pct)
         ├─ backtest_stats.yearly_table(rows)
         ├─ backtest_stats.block_bootstrap_ci(...)  (3 applications)
         ├─ backtest_stats.strategy_with_costs(rows, cost_bps)
         └─ backtest_report.build_report()  →  docs/backtest-report.md
```

`BacktestRow` and `StrategyResult` TypedDicts move from being private to
`backtest_report.py` to being importable by `backtest_stats.py` (import
direction: `backtest_report` → `backtest_stats`; the shared types live in
`backtest_stats.py` and `backtest_report.py` re-imports them, so there is no
circular import).

## Components

### 1. Vol-targeting baseline (`vol_target_strategy`)

- Daily SPY returns come from `fwd1` (day T close → T+1 close). Realized vol at
  day T uses the trailing 20 daily returns ending at T (no lookahead:
  `fwd1[T-20 .. T-1]`).
- Exposure rule: `exposure_t = clamp(k / realized_vol_t, 0, 1)`.
- Calibration: bisection on `k` so the strategy's average exposure matches the
  timing strategy's exposure (e.g., 63% full sample, 69% validation window),
  to within ±0.5 percentage points. Deterministic, no randomness.
- Simulation mirrors the existing 5-day block convention in
  `backtest_report.strategy()`: non-overlapping 5-day holds, exposure fixed at
  the block's first day, block return = `exposure * fwd5 / 100`.
- First 20 rows (vol warmup) are simulated at the calibrated average exposure
  so all strategies cover identical date ranges.
- Output: a `StrategyResult` labeled
  `Vol-target {exp}% (no pillars, matched benchmark)` — appears in both
  strategy comparison tables directly under the matched constant benchmark.

### 2. Year-by-year table (`yearly_table`)

Per calendar year (rows grouped by `date[:4]`):

| Column | Definition |
|---|---|
| Year | calendar year |
| Days | scored trading days |
| Mean score | mean of `total` |
| Score ≥ 55 return | timing rule compounded over the year's blocks |
| Matched const. return | constant-fraction benchmark, same year |
| Vol-target return | vol-target baseline, same year |
| Buy & hold return | 100% SPY, same year |
| Beat benchmark? | ✓ / ✗ vs matched constant benchmark |

Yearly returns reuse the same 5-day block simulation restricted to the year's
rows (block boundaries reset at year start; acceptable approximation, noted in
report). The matched-benchmark exposure fraction and the vol-target `k` are the
**full-sample** calibrations, so year rows are comparable down the column.

### 3. Block bootstrap CIs (`block_bootstrap_ci`)

- Moving-block bootstrap: resample blocks of 21 consecutive rows (with
  replacement) until reaching n rows; compute the statistic per resample.
- 2,000 resamples, `random.Random(20260611)` fixed seed → deterministic output.
- 95% CI = 2.5th/97.5th percentiles of the resample distribution.
- Applied to exactly three statistics:
  - (a) Spearman IC of `total` vs forward return, horizons 1/5/20.
  - (b) Mean `fwd5` per decision band (5 bands).
  - (c) Decile-1 minus decile-10 mean `fwd5` spread (decile membership
    recomputed inside each resample).
- Report annotation: each value shows `[lo, hi]` and a `zero excluded: yes/no`
  marker. Runtime target: under ~30s pure Python for all applications
  combined; if (b)+(c) push past that, resamples for those drop to 1,000
  (seeded, still deterministic).

### 4. Transaction costs (`strategy_with_costs`)

- Cost model: `cost_bps` charged on each **change in exposure**, i.e.
  `cost = |exposure_new - exposure_old| * cost_bps / 10_000`, deducted from
  block return. Entering from cash to 100% costs the full rate; the binary
  timing rule pays on every flip; the constant benchmark pays once at
  inception; the vol-target baseline pays on its (smaller, continuous)
  exposure adjustments.
- Report section: Score ≥ 55, its matched constant benchmark, and the
  vol-target baseline at 0 / 5 / 10 / 20 bps — total return and Sharpe per
  cost level, plus a flip-count line for the timing rule.

## Report changes (`backtest_report.py`)

- Strategy comparison tables (both windows) gain the vol-target row.
- New sections, in order, after the validation strategy table:
  1. `## Year-By-Year` (table + one-line takeaway: count of years the rule
     beat its benchmark)
  2. `## Statistical Significance` (the three bootstrap tables)
  3. `## Transaction Cost Sensitivity`
- Executive Readout gains one line stating the vol-target verdict (whether the
  score beat the no-pillar vol dial) and one line on cost impact at 10 bps.
- Limitations section: remove the now-addressed cost bullet, replace with
  precise wording (costs modeled as linear bps on exposure change; no market
  impact or borrow).

## Error handling

- Same contract as today: `build_report` raises `ValueError` below 30 rows.
- `vol_target_strategy` raises `ValueError` if calibration cannot reach the
  target exposure within bounds (k searched over a wide fixed bracket).
- Bootstrap functions raise `ValueError` if rows < 2 blocks.
- All functions are pure; no I/O, no network, no clock reads (the existing
  `date.today()` stamp in the report header is unchanged).

## Testing

- New `test_backtest_stats.py`, same style as existing test files (stdlib
  asserts, runnable via `python3 test_backtest_stats.py`):
  - vol targeting: no-lookahead check (perturbing future returns does not
    change today's exposure), exposure matches target within tolerance,
    constant-vol input yields constant exposure.
  - yearly table: synthetic 2-year fixture with known returns; columns sum to
    full-sample compounding within tolerance.
  - bootstrap: deterministic across runs (same seed), CI contains the point
    estimate, degenerate input (constant series) yields zero-width CI,
    known-signal fixture excludes zero.
  - costs: 0 bps reproduces the existing `strategy()` result exactly;
    monotonic — higher bps never increases return; flip count matches a
    hand-computed fixture.
- `test_backtest_report.py` gains section-presence and ordering assertions for
  the three new sections plus the vol-target table row.
- CI: add `test_backtest_stats.py` to the test command in CLAUDE.md and the
  GitHub Actions workflow.

## Out of scope

- Product/UI repositioning (separate spec).
- Changes to `backtest.py`, the replay, or the CSV schema.
- VIX-threshold baseline variant (realized-vol targeting is the decisive
  test; VIX history is not in the CSV).
- Third-party dependencies (numpy/scipy) — repo is stdlib-only by design.
