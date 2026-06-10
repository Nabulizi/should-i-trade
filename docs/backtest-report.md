# Backtest Report

_Generated 2026-06-10 · engine edc22bb_

This report is generated from the per-day replay output produced by `backtest.py`.
It supports the product claim that the Market Quality Score is a risk/exposure dial, not a day-by-day return predictor.

## Executive Readout

- Full sample: 5,373 trading days from 2005-01-03 to 2026-05-12.
- Validation window (2016-01-04 to 2026-05-12): Score >= 55 produced +131.1% total return with 0.86 Sharpe, -14.3% max drawdown, and 69% market exposure.
- A constant 69%-SPY baseline (same risk budget, no timing) returned +188.8% with 0.96 Sharpe — the fair benchmark for the timing rule.
- Same-window buy & hold: +340.3% total return with 0.96 Sharpe and -31.7% max drawdown.
- Forward-return IC remains low (-0.078 at 5 days), so the score should not be marketed as a precise return forecast.

## Dataset

| Field | Value |
|---|---:|
| Source CSV | `backtest_results.csv` |
| Trading days | 5,373 |
| First scored day | 2005-01-03 |
| Last scored day | 2026-05-12 |

## Information Coefficient

Spearman correlation between the total score and forward SPY returns.

| Horizon | IC |
|---|---:|
| 1 trading day | -0.042 |
| 5 trading day | -0.078 |
| 20 trading day | -0.093 |

## 5-Day Return By Decision Band

Mean/Std (last column) is mean return divided by standard deviation — a volatility-adjusted signal quality score.
Values above +0.15 indicate the band has a meaningful directional edge relative to its own noise.

| Band | Days | Mean | Median | Hit Rate | Std Dev | Mean/Std |
|---|---:|---:|---:|---:|---:|---:|
| RISK-ON | 919 | +0.20% | +0.38% | 62.7% | 1.47% | +0.134 |
| CONSTRUCTIVE | 1,422 | +0.09% | +0.26% | 56.9% | 1.62% | +0.053 |
| SELECTIVE | 1,078 | +0.25% | +0.41% | 61.1% | 1.78% | +0.140 |
| DE-RISK | 893 | +0.30% | +0.62% | 61.0% | 2.60% | +0.117 |
| RISK-OFF | 1,061 | +0.40% | +0.61% | 59.5% | 3.84% | +0.104 |

## Score Deciles

| Decile | Score Range | Days | Mean 5D Return | Hit Rate |
|---:|---:|---:|---:|---:|
| 1 | 3-25 | 537 | +0.54% | 58.8% |
| 2 | 25-40 | 537 | +0.25% | 60.1% |
| 3 | 40-52 | 537 | +0.29% | 59.6% |
| 4 | 52-58 | 538 | +0.32% | 61.9% |
| 5 | 58-65 | 537 | +0.29% | 62.2% |
| 6 | 65-72 | 537 | +0.15% | 60.0% |
| 7 | 72-78 | 538 | +0.14% | 56.9% |
| 8 | 78-83 | 537 | +0.12% | 58.7% |
| 9 | 83-88 | 537 | +0.11% | 59.8% |
| 10 | 88-97 | 538 | +0.15% | 61.3% |

## Per-Pillar IC

| Pillar | IC 5D | IC 20D |
|---|---:|---:|
| Volatility | -0.087 | -0.119 |
| Trend | -0.069 | -0.093 |
| Breadth | -0.070 | -0.076 |
| Momentum | -0.027 | -0.004 |
| Macro | +0.039 | +0.059 |
| TOTAL | -0.078 | -0.093 |

## Regime Split

| Regime | Days | IC 5D | Mean 5D Return |
|---|---:|---:|---:|
| Bull tape (SPY > 200d) | 4,300 | -0.072 | +0.22% |
| Bear tape (SPY < 200d) | 1,073 | -0.037 | +0.32% |

## Strategy Comparison - Full Sample

Non-overlapping 5-trading-day holds. Each timing strategy is paired with a constant-fraction SPY baseline
that holds the same market exposure with no timing skill. Beat the matched baseline to demonstrate alpha.

| Strategy | Total Return | CAGR | Sharpe | Max Drawdown | Exposure |
|---|---:|---:|---:|---:|---:|
| Score >= 70 (CONSTRUCTIVE+) | +62.2% | +2.29% | 0.38 | -18.3% | 41% |
| Constant 41% SPY (matched benchmark) | +167.5% | +4.72% | 0.69 | -26.1% | 41% |
| Score >= 55 (SELECTIVE+) | +229.0% | +5.74% | 0.69 | -21.4% | 63% |
| Constant 63% SPY (matched benchmark) | +328.8% | +7.07% | 0.69 | -37.6% | 63% |
| Buy & hold | +808.3% | +10.90% | 0.69 | -54.2% | 100% |

## Strategy Comparison - Validation Window (2016-01-04 to 2026-05-12)

| Strategy | Total Return | CAGR | Sharpe | Max Drawdown | Exposure |
|---|---:|---:|---:|---:|---:|
| Score >= 70 (CONSTRUCTIVE+) | +78.0% | +5.74% | 0.77 | -13.2% | 46% |
| Constant 46% SPY (matched benchmark) | +106.4% | +7.26% | 0.96 | -15.7% | 46% |
| Score >= 55 (SELECTIVE+) | +131.1% | +8.45% | 0.86 | -14.3% | 69% |
| Constant 69% SPY (matched benchmark) | +188.8% | +10.81% | 0.96 | -22.9% | 69% |
| Buy & hold | +340.3% | +15.43% | 0.96 | -31.7% | 100% |

## Product Interpretation

- Keep the UI language centered on exposure quality and drawdown control.
- Treat 55 as the validated engagement line; 70 is a stronger constructive regime, not the first usable signal.
- Avoid claims that the score predicts individual profitable days.
- Rerun the replay and regenerate this report whenever scoring formulas, weights, thresholds, or safety overrides change.

## Limitations

- No trading costs, slippage, taxes, or execution delays.
- SPY close-to-close returns only; no intraday fills, stops, or position management.
- Calendar overlays are neutralized in the replay methodology.
- Historical data vendor revisions can change results.
- The score pillars are correlated, so the dashboard should not imply five fully independent votes.
