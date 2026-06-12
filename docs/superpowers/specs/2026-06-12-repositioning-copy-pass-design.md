# Repositioning Copy Pass — Design

Date: 2026-06-12
Status: Approved design, pending spec review
Branch: `feat/repositioning-copy-pass` (stacked on `feat/backtest-robustness-analytics`, PR #40)

## Problem

The robustness analytics (PR #40) falsified the product's remaining performance
claim: a no-pillar vol-target baseline at matched exposure beats the Score ≥ 55
timing rule on return, Sharpe, AND max drawdown (validation window: 1.06 vs
0.86 Sharpe, −11.1% vs −14.3% max DD); the rule beat its fair benchmark in only
6 of 22 years; the contrarian decile spread is statistically indistinguishable
from zero. Several copy surfaces still claim or imply a timing/drawdown edge.

This is an **honest copy pass**: every claim the data no longer supports is
rewritten. Band names, thresholds, colors, layout, payloads, and all behavior
are unchanged. Codex's draft copy (commit `aba5720`) is the starting point
where it exists, tightened against the final numbers.

Voice decision: keep the trading-desk coach voice in band action strings, but
strip outcome promises. Conditions adjectives replace regime-outcome claims.

## Changes by file

### 1. `scoring.py`

Header comment above `DECISION_BANDS` becomes:

```python
# Market-conditions gauge: the 2005-2026 replay (docs/backtest-report.md) shows
# the composite describes the current regime but has no demonstrated timing
# edge over same-exposure baselines. Labels describe conditions and a suggested
# exposure posture; they are not validated trade signals. 55/70/85 are
# descriptive bands, not proven thresholds.
```

The five `action` strings become (names/min/color/position unchanged):

| Band | New action string |
|---|---|
| RISK-ON | `Full exposure — calm, trending tape, press the bid on A/B setups` |
| CONSTRUCTIVE | `Standard exposure — constructive tape, run your normal game` |
| SELECTIVE | `Moderate exposure — mixed tape, engage selectively, A+ setups, tight stops` |
| DE-RISK | `Reduced exposure — choppy tape, very selective or sit out` |
| RISK-OFF | `Defensive — stressed tape, protect capital, no new longs` |

Rationale: "low-drawdown regime" (RISK-ON) and "drawdown risk elevated"
(RISK-OFF) are outcome predictions the report does not support; tape
adjectives (calm/constructive/mixed/choppy/stressed) are condition
descriptions the pillars actually measure.

### 2. `static/app.js`

The fallback action ternary (~lines 203–207) is updated to byte-match the five
new `scoring.py` strings. The band table (~line 636), zone function (~1074),
and emoji map (~1113) are unchanged (they contain no unsupported claims).

### 3. `should-i-trade-v6.html`

The score legend currently shows `70+: RISK-ON (full / standard exposure)`,
which is wrong even today (RISK-ON starts at 85). Replace that line with two
accurate lines: `85+: RISK-ON (full exposure)` and `70+: CONSTRUCTIVE
(standard exposure)`, matching the surrounding legend markup style.

### 4. `README.md`

a) The "What the score is (and isn't)" blockquote is replaced with:

> **What the score is (and isn't).** The composite Market Quality Score
> describes market conditions; it is **not a timing signal**. In the 2005–2026
> backtest, a no-pillar volatility-targeting baseline holding the same average
> exposure beat the "long SPY when score ≥ 55" rule on total return, Sharpe,
> and max drawdown (validation window: 1.06 vs 0.86 Sharpe, −11.1% vs −14.3%
> max drawdown). The rule beat its fair benchmark in 6 of 22 years, and
> forward-return correlations are negative. Read the dashboard as a conditions
> report and exposure prompt — see the [Backtest Report](docs/backtest-report.md)
> for the full evidence.

b) The intro tagline keeps Codex's "market-conditions gauge" phrasing.

c) The correlation note drops the unsourced r-values and the "score still
works as a drawdown timer" sentence; it becomes:

> **Correlation note:** the five pillars are substantially correlated — the
> composite behaves like roughly three effective inputs, not five independent
> votes. Macro is the most independent pillar. Don't read the five bars as
> five separate confirmations.

d) First-Run Orientation bullet becomes: "Read the score as a
conditions/exposure dial: **55/70/85** mark descriptive bands (selective /
constructive / strongest), not validated signal thresholds."

e) Project-structure tree gains `backtest_stats.py` ("Pure offline stats:
baselines, bootstrap CIs, costs") and `test_backtest_stats.py`; the test
commands section adds `python3 test_backtest_stats.py`.

### 5. `docs/backtest-methodology.md`

Adopt Codex's draft headline-claim section (conservative bullets), plus one
added bullet stating the decisive result:

> - A no-pillar volatility-targeting baseline at matched exposure outperformed
>   the score-timing rule on return, Sharpe, and max drawdown in the validation
>   window; treat any timing claim as unsupported until this baseline is beaten
>   out of sample.

Also adopt Codex's expanded "Metrics To Check" list (same content as its
draft: same-exposure baseline, vol-target baseline, year-by-year, bootstrap
CIs, cost sensitivity).

### 6. `CLAUDE.md`

The stale line `Decision thresholds: ≥85 STRONG YES → 70 YES → 55 CAUTION →
40 NO → <40 WAIT.` becomes:
`Decision bands: ≥85 RISK-ON → 70 CONSTRUCTIVE → 55 SELECTIVE → 40 DE-RISK →
<40 RISK-OFF (descriptive bands, not validated thresholds).`

## Claim-hygiene test

New test in `test_scoring.py` (offline, stdlib): assert that none of the
banned phrases appear in (a) `scoring.py` source, (b) `README.md`, (c)
`docs/backtest-methodology.md`, (d) `CLAUDE.md`:

Banned phrases: `low-drawdown regime`, `drawdown timer`,
`drawdown/exposure timer`, `drawdown risk elevated`, `validated engagement
line`, `STRONG YES`.

Plus an assertion that every `DECISION_BANDS` action string is non-empty and
under 90 characters (badge-width guard).

`static/app.test.js` is checked during implementation; no current test pins
the old strings, so JS changes only if a test actually references them.

## Out of scope

- Band renames, threshold values, colors, payload schema, UI layout.
- Screenshots.
- The Codex branch's other content (already ported or superseded).
- `docs/backtest-report.md` (generated file; regenerating is not needed —
  no generator code changes here).

## Testing / verification

- Full Python suite + `npm test` + `npm run lint` green.
- `git diff` confined to the six files above + `test_scoring.py`.
- Manual smoke: load the dashboard, confirm badge strings render and fit.
