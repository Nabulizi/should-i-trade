# Backtest Methodology

This document records how the Market Quality Score claims should be reproduced
and interpreted. The dashboard is a risk/exposure gauge, not a return predictor
or financial advice.

## Current Headline Claim

The README summarizes a 2005-2026 walk-forward replay showing that the
composite score is most useful as a drawdown/exposure timer:

- Higher scores did not reliably predict which individual days would be
  profitable.
- A rule that stayed long SPY when the score cleared the engagement threshold
  and de-risked when it did not improved risk-adjusted results versus
  buy-and-hold in the documented out-of-sample window.
- The validated engagement threshold is 55, not 70.

Keep this claim attached to the exact implementation in `backtest.py` and the
current scoring engine. If scoring rules or thresholds change, rerun and update
this document before strengthening any public claim.

## Reproduction Command

```bash
python3 backtest.py
```

Use this when the cached historical data in `.backtest_cache/` is acceptable.
To force a fresh Yahoo download:

```bash
python3 backtest.py --refresh
```

The script writes per-day results to `backtest_results.csv`, which is ignored by
git because it is generated output.

## Replay Design

The replay reconstructs each historical trading day after the warmup window:

- Downloads adjusted daily closes for the instruments used by the live engine.
- Aligns symbols to the SPY trading-day calendar.
- Rebuilds the quote/history inputs using only data through day T.
- Calls the real pillar functions in `scoring.py`.
- Applies the live pillar weights and the VIX / below-200d safety overrides.
- Measures SPY forward returns from day T close to T+1, T+5, and T+20.

The score is evaluated as a close-to-forward regime signal. It is not an
intraday execution simulation.

## Neutralized Inputs

Date-deterministic overlays are neutralized in the replay:

- FOMC proximity
- OpEx proximity
- Monthly seasonality

Those overlays use current-date logic and hand-maintained future calendars, so
they are intentionally excluded from the historical hypothesis test. The market
data pillars and safety overrides remain active.

## Metrics To Check

When validating a change, inspect at least:

- Information coefficient between score and 1d/5d/20d forward SPY returns.
- Forward 5-day return by decision band.
- Score decile monotonicity.
- Per-pillar information coefficient.
- Year-by-year behavior, especially weak market years.
- Bull versus bear regime split.
- Strategy test versus buy-and-hold, including exposure, Sharpe, and max
  drawdown.

Do not rely only on total return. A de-risking tool earns its keep by reducing
bad exposure, not by forecasting every profitable period.

## Known Limitations

- No trading costs, slippage, borrow costs, taxes, or execution delays.
- Uses SPY daily close-to-close returns, not intraday entries or stops.
- Uses Yahoo historical data and available ETF history; source revisions can
  change results.
- The symbol universe changes over time in the real world; the replay does not
  fully model survivorship or product availability issues.
- Calendar/event overlays are excluded from historical scoring.
- The scoring engine has correlated pillars, so the five bars should not be
  interpreted as five independent votes.
- Strategy results can be sensitive to the chosen rebalance cadence and
  threshold.

## Update Protocol

Update this document when any of these change:

- Pillar formulas or weights.
- Decision thresholds.
- Safety override caps.
- Backtest date range, warmup, horizons, or data source.
- README headline performance claims.

Recommended commit discipline:

1. Run the Python and JS test suites.
2. Run `python3 backtest.py`.
3. Compare headline metrics against the previous run.
4. Update README claims only when the new evidence still supports them.
