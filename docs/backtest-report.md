# Backtest Report

_Generated 2026-06-12 · engine 2534f14_

This report is generated from the per-day replay output produced by `backtest.py`.
It tests whether the Market Quality Score adds timing value after fair same-exposure baselines.
Product copy should stay conservative unless the timing rule clears those baselines out of sample.

## Executive Readout

- Full sample: 5,375 trading days from 2005-01-03 to 2026-05-14.
- Validation window (2016-01-04 to 2026-05-14): Score >= 55 produced +129.4% total return with 0.85 Sharpe, -14.3% max drawdown, and 70% market exposure.
- A constant 70%-SPY baseline (same risk budget, no timing) returned +187.6% with 0.95 Sharpe — the fair benchmark for the timing rule.
- Timing edge versus constant exposure: -58.2% total-return points and -0.10 Sharpe. Drawdown difference: +8.6% (positive means the timing rule drew down less).
- A same-window, no-pillar vol-target baseline at the same exposure returned +152.4% with 1.05 Sharpe and -11.1% max drawdown. Timing edge versus vol-target: -23.0% total-return points and -0.20 Sharpe.
- At 10 bps per exposure change (263 flips), the full-sample Score >= 55 total return drops to +152.9%.
- Conditions hypothesis (cleaner next-session trends after high scores): **FAIL** — range-efficiency decile spread -0.039, 95% CI [-0.074, -0.005].
- Same-window buy & hold: +337.1% total return with 0.95 Sharpe and -31.7% max drawdown.
- Forward-return IC remains low (-0.078 at 5 days), so the score should not be marketed as a precise return forecast.

## Dataset

| Field | Value |
|---|---:|
| Source CSV | `backtest_results.csv` |
| Trading days | 5,375 |
| First scored day | 2005-01-03 |
| Last scored day | 2026-05-14 |

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
| CONSTRUCTIVE | 1,424 | +0.09% | +0.25% | 56.8% | 1.62% | +0.053 |
| SELECTIVE | 1,078 | +0.25% | +0.41% | 61.1% | 1.78% | +0.140 |
| DE-RISK | 893 | +0.30% | +0.62% | 61.0% | 2.60% | +0.117 |
| RISK-OFF | 1,061 | +0.40% | +0.61% | 59.5% | 3.84% | +0.104 |

## Score Deciles

| Decile | Score Range | Days | Mean 5D Return | Hit Rate |
|---:|---:|---:|---:|---:|
| 1 | 3-25 | 537 | +0.54% | 58.8% |
| 2 | 25-40 | 538 | +0.25% | 60.2% |
| 3 | 40-52 | 537 | +0.29% | 59.6% |
| 4 | 52-58 | 538 | +0.33% | 61.9% |
| 5 | 58-65 | 537 | +0.29% | 62.2% |
| 6 | 65-72 | 538 | +0.15% | 59.9% |
| 7 | 72-78 | 537 | +0.14% | 56.8% |
| 8 | 78-83 | 538 | +0.12% | 58.6% |
| 9 | 83-88 | 537 | +0.11% | 59.8% |
| 10 | 88-97 | 538 | +0.15% | 61.3% |

## Per-Pillar IC

| Pillar | IC 5D | IC 20D |
|---|---:|---:|
| Volatility | -0.087 | -0.119 |
| Trend | -0.069 | -0.093 |
| Breadth | -0.070 | -0.076 |
| Momentum | -0.027 | -0.004 |
| Macro | +0.040 | +0.059 |
| TOTAL | -0.078 | -0.093 |

## Regime Split

| Regime | Days | IC 5D | Mean 5D Return |
|---|---:|---:|---:|
| Bull tape (SPY > 200d) | 4,302 | -0.072 | +0.22% |
| Bear tape (SPY < 200d) | 1,073 | -0.038 | +0.32% |

## Strategy Comparison - Full Sample

Non-overlapping 5-trading-day holds. Each timing strategy is paired with a constant-fraction SPY baseline
that holds the same market exposure with no timing skill. Beat the matched baseline to demonstrate alpha.

| Strategy | Total Return | CAGR | Sharpe | Max Drawdown | Exposure |
|---|---:|---:|---:|---:|---:|
| Score >= 70 (CONSTRUCTIVE+) | +62.2% | +2.29% | 0.38 | -18.3% | 41% |
| Constant 41% SPY (matched benchmark) | +167.5% | +4.72% | 0.69 | -26.1% | 41% |
| Score >= 55 (SELECTIVE+) | +229.0% | +5.74% | 0.69 | -21.4% | 63% |
| Constant 63% SPY (matched benchmark) | +328.8% | +7.06% | 0.69 | -37.6% | 63% |
| Vol-target 63% (no pillars, matched benchmark) | +294.0% | +6.64% | 0.84 | -20.0% | 63% |
| Buy & hold | +808.3% | +10.90% | 0.69 | -54.2% | 100% |

## Strategy Comparison - Validation Window (2016-01-04 to 2026-05-14)

| Strategy | Total Return | CAGR | Sharpe | Max Drawdown | Exposure |
|---|---:|---:|---:|---:|---:|
| Score >= 70 (CONSTRUCTIVE+) | +76.7% | +5.66% | 0.76 | -13.2% | 47% |
| Constant 47% SPY (matched benchmark) | +106.0% | +7.24% | 0.95 | -15.8% | 47% |
| Score >= 55 (SELECTIVE+) | +129.4% | +8.36% | 0.85 | -14.3% | 70% |
| Constant 70% SPY (matched benchmark) | +187.6% | +10.76% | 0.95 | -22.9% | 70% |
| Vol-target 70% (no pillars, matched benchmark) | +152.4% | +9.37% | 1.05 | -11.1% | 70% |
| Buy & hold | +337.1% | +15.33% | 0.95 | -31.7% | 100% |

## Year-By-Year

Calendar-year returns. Matched-benchmark fraction and vol-target calibration are full-sample (63% exposure), so rows are comparable down each column. Block boundaries reset at year start (approximation).

The Score >= 55 rule beat its matched benchmark in **6 of 22 years**.

| Year | Days | Avg Exposure | Score >= 55 Ret | Score >= 55 Max DD | Matched Ret | Matched Max DD | Vol-Target Ret | Buy & Hold Ret | Beat benchmark? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 2005 | 252 | 69% | +1.7% | -6.0% | +5.4% | -3.4% | +5.5% | +8.6% | ✗ |
| 2006 | 251 | 76% | +5.4% | -6.3% | +8.3% | -4.1% | +12.7% | +13.4% | ✗ |
| 2007 | 251 | 71% | -10.0% | -12.4% | +0.3% | -6.4% | -0.3% | +0.1% | ✗ |
| 2008 | 253 | 2% | -3.1% | -3.1% | -21.5% | -32.0% | -10.6% | -34.0% | ✓ |
| 2009 | 252 | 49% | +12.5% | -4.7% | +16.2% | -16.0% | +10.7% | +25.7% | ✗ |
| 2010 | 252 | 63% | -1.0% | -12.9% | +9.4% | -9.7% | +10.4% | +14.6% | ✗ |
| 2011 | 252 | 47% | -9.3% | -14.4% | +2.4% | -10.8% | -1.1% | +2.6% | ✗ |
| 2012 | 250 | 66% | +4.4% | -8.7% | +10.6% | -5.5% | +10.6% | +17.1% | ✗ |
| 2013 | 252 | 86% | +25.0% | -5.8% | +16.9% | -2.8% | +15.4% | +28.2% | ✓ |
| 2014 | 252 | 71% | -0.8% | -6.9% | +8.0% | -3.8% | +5.3% | +12.8% | ✗ |
| 2015 | 252 | 53% | -7.1% | -12.1% | -2.0% | -7.0% | -4.0% | -3.6% | ✗ |
| 2016 | 252 | 63% | +8.3% | -3.1% | +9.6% | -4.9% | +8.0% | +15.5% | ✗ |
| 2017 | 251 | 94% | +19.5% | -2.1% | +14.5% | -1.3% | +22.8% | +24.0% | ✓ |
| 2018 | 251 | 63% | -2.0% | -8.4% | -1.3% | -10.8% | +0.2% | -2.7% | ✗ |
| 2019 | 252 | 75% | +20.6% | -4.4% | +18.9% | -3.7% | +13.0% | +31.4% | ✓ |
| 2020 | 253 | 61% | +13.0% | -6.8% | +11.7% | -22.2% | +5.8% | +17.1% | ✓ |
| 2021 | 252 | 84% | +12.7% | -4.0% | +17.3% | -2.5% | +14.4% | +28.6% | ✗ |
| 2022 | 251 | 18% | -15.4% | -15.4% | -10.8% | -15.7% | -6.8% | -17.5% | ✗ |
| 2023 | 250 | 66% | +10.9% | -5.8% | +15.8% | -5.8% | +13.4% | +26.0% | ✗ |
| 2024 | 252 | 78% | +5.1% | -9.5% | +15.9% | -4.8% | +14.7% | +26.1% | ✗ |
| 2025 | 250 | 64% | +6.3% | -6.5% | +11.6% | -11.9% | +6.5% | +18.2% | ✗ |
| 2026 | 92 | 68% | +8.5% | -2.8% | +5.5% | -3.9% | +4.0% | +8.8% | ✓ |

## Statistical Significance

Moving-block bootstrap (block 21 days, seeded, 95% CI). "Zero excluded: no" means
the value is statistically indistinguishable from noise at this sample size.

| Statistic | Point | 95% CI | Zero excluded |
|---|---:|---:|:---:|
| IC (1d) | -0.042 | [-0.067, -0.016] | yes |
| IC (5d) | -0.078 | [-0.126, -0.035] | yes |
| IC (20d) | -0.093 | [-0.170, -0.021] | yes |
| Mean 5D, RISK-ON | +0.20% | [+0.08%, +0.31%] | yes |
| Mean 5D, CONSTRUCTIVE | +0.09% | [-0.03%, +0.20%] | no |
| Mean 5D, SELECTIVE | +0.25% | [+0.11%, +0.39%] | yes |
| Mean 5D, DE-RISK | +0.30% | [+0.06%, +0.55%] | yes |
| Mean 5D, RISK-OFF | +0.40% | [+0.03%, +0.79%] | yes |
| Mean 5D, score decile 1 | +0.54% | [+0.04%, +1.05%] | yes |
| Mean 5D, score decile 2 | +0.25% | [-0.12%, +0.66%] | no |
| Mean 5D, score decile 3 | +0.29% | [-0.09%, +0.54%] | no |
| Mean 5D, score decile 4 | +0.33% | [+0.05%, +0.61%] | yes |
| Mean 5D, score decile 5 | +0.29% | [+0.08%, +0.41%] | yes |
| Mean 5D, score decile 6 | +0.15% | [+0.01%, +0.34%] | yes |
| Mean 5D, score decile 7 | +0.14% | [-0.04%, +0.30%] | no |
| Mean 5D, score decile 8 | +0.12% | [-0.03%, +0.25%] | no |
| Mean 5D, score decile 9 | +0.11% | [-0.09%, +0.26%] | no |
| Mean 5D, score decile 10 | +0.15% | [+0.01%, +0.32%] | yes |
| Decile 1 - Decile 10 spread (5D) | +0.38% | [-0.14%, +0.89%] | no |

## Transaction Cost / Slippage Sensitivity

Costs/slippage are charged on each change in exposure (including initial entry):
cost = |delta exposure| x bps / 10,000. The constant benchmark pays once at
inception; the vol-target baseline pays on its smaller continuous adjustments.

The Score >= 55 rule made **263 exposure flips** over this sample.

| Strategy | 0 bps | 5 bps | 10 bps | 20 bps |
|---|---:|---:|---:|---:|
| Score >= 55 (SELECTIVE+) | +229.0% (S 0.69) | +188.5% (S 0.62) | +152.9% (S 0.55) | +94.4% (S 0.40) |
| Constant 63% SPY | +328.8% (S 0.69) | +328.7% (S 0.69) | +328.5% (S 0.69) | +328.3% (S 0.69) |
| Vol-target 63% | +294.0% (S 0.84) | +280.2% (S 0.81) | +266.9% (S 0.79) | +241.6% (S 0.75) |

## Next-Session Trading Conditions

Does a high score predict a better session to TRADE (not a higher return)?
Metrics describe SPY's next session from raw daily OHLC: range efficiency
|C-O|/(H-L) (1.0 = clean trend day, ~0 = round-trip chop), range size (H-L)/prevC,
gap share (fraction of the move that happened overnight, untradeable), and
trend-day frequency (efficiency > 0.6).

**Pre-registered H1:** next-session range efficiency is higher after
top-decile score days than after bottom-decile days (95% block-bootstrap
CI of the decile spread excludes zero, positive direction).

Spread -0.039, 95% CI [-0.074, -0.005].

**VERDICT: FAIL**

| Band | Valid Days | Range Eff | Range Size | Gap Share | Trend Days |
|---|---:|---:|---:|---:|---:|
| RISK-ON | 919 | 0.431 | 0.76% | 0.348 | 29.5% |
| CONSTRUCTIVE | 1,424 | 0.441 | 0.85% | 0.364 | 30.6% |
| SELECTIVE | 1,078 | 0.470 | 1.00% | 0.389 | 35.4% |
| DE-RISK | 893 | 0.482 | 1.43% | 0.374 | 37.3% |
| RISK-OFF | 1,061 | 0.478 | 2.22% | 0.363 | 36.1% |

| Decile | Valid Days | Range Eff | Range Size | Gap Share | Trend Days |
|---:|---:|---:|---:|---:|---:|
| 1 | 537 | 0.462 | 2.55% | 0.361 | 34.1% |
| 2 | 538 | 0.494 | 1.88% | 0.366 | 38.1% |
| 3 | 537 | 0.482 | 1.43% | 0.364 | 36.7% |
| 4 | 538 | 0.487 | 1.32% | 0.389 | 38.8% |
| 5 | 537 | 0.469 | 0.97% | 0.388 | 34.3% |
| 6 | 538 | 0.466 | 0.93% | 0.374 | 34.6% |
| 7 | 537 | 0.438 | 0.85% | 0.379 | 30.5% |
| 8 | 538 | 0.435 | 0.83% | 0.364 | 30.7% |
| 9 | 537 | 0.438 | 0.81% | 0.332 | 29.4% |
| 10 | 538 | 0.422 | 0.73% | 0.360 | 28.6% |

Decile 10 minus decile 1 spreads (positive = high score better):

| Metric | Point | 95% CI | Zero excluded |
|---|---:|---:|:---:|
| Range efficiency (PRIMARY) | -0.039 | [-0.074, -0.005] | yes |
| Range size (descriptive) | -0.018 | [-0.023, -0.014] | yes |
| Gap share (descriptive) | -0.001 | [-0.042, +0.033] | no |
| Trend-day rate (descriptive) | -0.054 | [-0.121, +0.006] | no |

## Product Interpretation

- Keep the UI language centered on market conditions, exposure quality, and drawdown control.
- If the score does not beat constant-exposure and vol-target baselines, describe it as a conditions dashboard rather than a timing edge.
- Treat 55 as the current tested engagement line; 70 is a stronger constructive regime, not the first usable signal.
- Avoid claims that the score predicts individual profitable days.
- Rerun the replay and regenerate this report whenever scoring formulas, weights, thresholds, or safety overrides change.

## Limitations

- Costs are modeled as linear bps on exposure changes only; no market impact, borrow, taxes, or execution delay.
- SPY close-to-close returns only; no intraday fills, stops, or position management.
- Calendar overlays are neutralized in the replay methodology.
- Historical data vendor revisions can change results.
- Condition metrics proxy intraday quality from daily OHLC; no true intraday bars.
- The gap metric uses raw prior close, so dividend days (~4/year) carry a small gap bias.
- The score pillars are correlated, so the dashboard should not imply five fully independent votes.
