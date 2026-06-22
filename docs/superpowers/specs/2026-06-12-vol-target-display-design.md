# Live Vol-Target Exposure Display — Design

Date: 2026-06-12
Status: Approved design, pending spec review
Branch: `feat/vol-target-display` (based on the merged #40–#42 chain)

## Problem

The backtest established that a no-pillar volatility-targeting dial beats the
score-timing rule on return, Sharpe, and max drawdown at the same exposure
(report: Strategy Comparison + Executive Readout). The dashboard should show
that number — it is the only figure in the product with evidence behind it.
The score's conditions narrative stays; the vol-target line sits beside it.

## Calibration: backtest-derived `k`

Live formula: `exposure = clamp(k / realized_vol, 0, 1)`.

- `k` is the constant the full-sample backtest bisection produced when
  matching the Score ≥ 55 rule's exposure (63% average, 2005–2026). Using
  that exact constant makes the displayed number literally "the baseline
  that won."
- `k` is currently internal to `backtest_stats.calibrate_vol_exposures`
  (the function returns exposures, not `k`). Implementation includes a
  one-off offline derivation: rerun the same bisection against
  `backtest_results.csv` and print `k`; the printed value is pinned in
  `config.py` with a provenance comment (derivation command, report
  section, date, value). The live path never bisects — one division per
  refresh.
- **Unit convention (critical):** the backtest's vol is `_std` of `fwd1`
  values, which are *percent* daily returns (e.g. `1.2` = 1.2%). The live
  computation must produce percent-unit returns
  (`(c[i]/c[i-1] - 1) * 100`) before taking the stdev, or the displayed
  exposure is silently wrong by ~100x. The spec pins this; tests enforce it
  with a hand-computed fixture.

## Changes by file

### 1. `config.py`

```python
# Vol-target exposure dial (see docs/backtest-report.md, Strategy Comparison).
# VOL_TARGET_K was derived offline on 2026-06-12 by re-running the full-sample
# bisection from backtest_stats.calibrate_vol_exposures against
# backtest_results.csv (2005-2026, matched to the Score>=55 rule's 63%
# average exposure). Units: percent daily-return volatility.
# Derivation: python3 -c "<snippet documented in the implementation plan>"
VOL_TARGET_K = <pinned value>   # filled by the implementation's derivation step
VOL_TARGET_WINDOW = 20          # trading days of realized vol
```

(`<pinned value>` is a plan-time derivation output, not a runtime
computation; the implementation plan contains the exact derivation snippet
and the implementer replaces the placeholder with the printed number.)

### 2. `scoring.py`

New pure function (near the other helpers):

```python
def vol_target_exposure(closes: list[float]) -> VolTargetInfo | None:
    """Evidence-backed exposure dial: clamp(k / realized vol, 0..100%).

    closes: chronological adjusted closes; needs VOL_TARGET_WINDOW + 1.
    Returns None when history is insufficient or volatility is zero.
    """
```

- Computes the last `VOL_TARGET_WINDOW` percent daily returns from the last
  `VOL_TARGET_WINDOW + 1` closes, sample stdev (n−1), then
  `exposure_pct = min(100.0, max(0.0, 100.0 * VOL_TARGET_K / vol))`.
- Returns `{"exposure_pct": ..., "realized_vol_pct": ...}` rounded to one
  decimal each.
- Wired into `compute_dashboard()`: reuses the SPY closes already fetched
  for the trend pillar (no new network call). Payload key: `"vol_target"`,
  value `VolTargetInfo | None`. On any missing/short history: `None`.

### 3. `models.py`

```python
class VolTargetInfo(TypedDict):
    exposure_pct: float
    realized_vol_pct: float
```

`DashboardResult` gains `vol_target: VolTargetInfo | None`.

### 4. Frontend (`static/app.js`, `should-i-trade-v6.html`)

- One companion line in the hero, directly under the action-hint/posture
  line, rendered by `app.js` from the dashboard payload:
  `Vol-target dial: ~72% exposure — no-pillar baseline that beat the score
  in the 2005–2026 backtest` (percentage live; `~` prefix; en dash copy
  exactly as shown, with a link-free reference to the report).
- Hidden entirely (display:none) when `vol_target` is `null` — no empty
  shells, matching how other degraded elements behave.
- Styling: same muted style as the posture line; no new layout containers
  beyond one element with an id (e.g. `vol-target-line`).

### 5. Tests

- `test_scoring.py` (existing `ok()` style):
  - hand-computed fixture: 21 closes alternating so percent returns are
    exactly ±1.0 → vol = stdev([+1,-1]*10) → exposure = 100*k/vol, assert
    to 6 decimals;
  - calm-market clamp: tiny vol → exposure exactly 100.0;
  - insufficient history (≤ VOL_TARGET_WINDOW closes) → None;
  - zero vol (constant closes) → None.
- `test_contracts.py`: `vol_target` key present in the dashboard payload;
  accepts both a well-formed dict (two float fields) and `None`.
- `static/app.test.js`: renders the percentage into the line; hides the
  element when `vol_target` is null.
- Claim-hygiene: the new UI copy contains no banned phrases (automatically
  enforced — `static/app.js` and the HTML are hygiene surfaces).

### 6. Error handling

Same contract as the pillars: any failure to produce the number yields
`None` in the payload and a hidden line in the UI. No exceptions can escape
`vol_target_exposure` (pure arithmetic with guards).

## Out of scope

- Changing `position_size`, score logic, or band copy.
- Configurable target vol or UI controls.
- README changes (the feature is self-describing in the UI; README touts
  it later if desired).
- Intraday/real-time vol (the 60s dashboard cache cadence is unchanged).

## Risks

- The pinned `k` goes stale if the backtest is recalibrated; the provenance
  comment ties it to a report version, and the methodology doc's update
  protocol already covers "rerun and update."
- `get_history` returns adjusted closes; the backtest's vol also used
  adjusted (fwd1 from adjclose) — consistent.
