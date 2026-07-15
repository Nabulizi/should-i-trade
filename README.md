<p align="center"><img src="assets/logo.svg" alt="Should I Trade? — Market Quality Terminal" width="520"></p>

# Should I Trade? — Market Quality Terminal v6

A single-page, self-hosted **market-conditions gauge** for the session: it reads the market regime and turns current conditions into a suggested exposure posture.

No subscriptions, no API keys, no cloud dependencies — all data comes from free public sources.

> **Live demo:** [should-i-trade.onrender.com](https://should-i-trade.onrender.com) — or self-host in one command (see Quick Start).

> **What the score is (and isn't).** The composite Market Quality Score describes market conditions; it is **not a timing signal**. In the 2005–2026 backtest, a no-pillar volatility-targeting baseline holding the same average exposure beat the "long SPY when score ≥ 55" rule on total return, Sharpe, and max drawdown (validation window: 1.06 vs 0.86 Sharpe, −11.1% vs −14.3% max drawdown). The rule beat its fair benchmark in 6 of 22 years, and forward-return correlations are negative. A preregistered follow-up (QR-010) supports the exposure-dial direction: low scores have historically preceded elevated short-term volatility — though a plain VIX quote predicted forward volatility better, so treat the score as an aggregated conditions read, not a superior signal. Read the dashboard as a conditions report and exposure prompt — see the [Backtest Report](docs/backtest-report.md) and the [methodology](docs/backtest-methodology.md) for the full evidence.

> See [Backtest Methodology](docs/backtest-methodology.md) and the generated [Backtest Report](docs/backtest-report.md) for reproduction commands, assumptions, results, and limitations.

> **Risk disclaimer.** This is an educational market-regime dashboard, not financial advice, investment advice, or a trading system. You are responsible for position sizing, execution, and losses.

---

## Screenshot

![Dashboard screenshot](docs/screenshot.png)

> Live dashboard running at `http://localhost:8765` — or try the **[live demo](https://should-i-trade.onrender.com)**

The dashboard shows a composite **Market Quality Score (0–100)**, five scoring pillars, a trading decision recommendation, and a multi-persona AI roundtable discussion. The server refreshes market data at most every 60 seconds (cache TTL); the page picks up changes via SSE push and re-polls every 5 minutes.

---

## Features

| Feature | Detail |
|---|---|
| **Market Quality Score** | 0–100 composite score across 5 weighted pillars |
| **5-Pillar Breakdown** | Volatility · Trend · Breadth · Momentum · Macro |
| **Risk Posture Badge** | RISK-ON / CONSTRUCTIVE / SELECTIVE / DE-RISK / RISK-OFF — exposure recommendation for the session |
| **Trading Desk Roundtable** | 5 rule-based AI personas (Technician, Macro, Risk, Quant, Desk Head) |
| **Score Sparkline** | 12-hour rolling history chart with persistent storage |
| **Economic Calendar** | FOMC & key econ event proximity alerts (through Dec 2027) |
| **Sector Heatmap** | All 11 SPDR sectors + 9 industry subsector ETFs |
| **Market Conditions** | SPY, QQQ, VIX, VIX3M, HYG, GLD, DXY, TLT, 10Y yield, BTC |
| **Daily Push Report** | Optional morning conditions report to Telegram / Discord (09:00 ET, trading days) |
| **Since-Yesterday Delta** | Day-over-day score, pillar, and posture-band changes vs previous close |
| **Watchlist Health** | Scores your personal watchlist symbols (TradingView format supported) |
| **Prospective Forecast Log** | Daily immutable EOD forecast records, graded next session against predeclared outcomes ([design](docs/prospective-log.md)) |
| **Health & Metrics** | `/health` and `/metrics` endpoints for monitoring |
| **Rate Limiting** | 30 req/min per IP — protects against runaway polling |
| **Responsive UI** | Works on mobile (≥320px) — simplified layout at ≤480px |
| **Zero API keys** | Yahoo Finance → Stooq → CoinGecko → Binance (all free) |

---

## Quick Start

### Requirements
- **Python 3.10+** (uses union type hints `X | Y` and `match` statements)
- **Core app: standard library only** — no pip install needed to run
- Optional: `pip install google-genai` + a free Gemini key enables the AI Desk Head
  (everything else works without it — rule-based roundtable is the fallback)
- Optional (dev only): Node 20 for JS lint/tests (`npm ci && npm test`)

### Run
```bash
git clone git@github.com:Nabulizi/should-i-trade.git
cd should-i-trade
python3 server.py
```

Then open **http://localhost:8765** in your browser. The first load takes ~7–8 seconds as it fetches live data for 33 symbols in parallel.

> The server auto-opens the browser on startup. Re-open manually if needed.

### First-Run Orientation

- The headline score is the backend's official Market Quality Score. Custom weights in the UI are what-if only and never rewrite the saved/live score.
- Read the score as a conditions/exposure dial: **55/70/85** mark descriptive bands (selective / constructive / strongest), not validated signal thresholds.
- If the data-quality banner appears, treat the decision as disabled or stale until live market inputs recover.
- The first full refresh is slower than later refreshes because the 60-second cache is empty.
- To use Watchlist Health, place a TradingView-format `.txt` export in `watchlists/` and refresh `/api/watchlist-health`. Personal exports are git-ignored; a generic `Watchlist_Example.txt` ships as the fallback default.

---

## Project Structure

```
should-i-trade/
├── server.py              # HTTP server, routing, caching, SSE, history persistence
├── scoring.py             # 5-pillar scoring engine (0–100 per pillar, weighted composite)
├── data.py                # Market data fetchers (Yahoo Finance + fallbacks, circuit breakers)
├── analysis.py            # Rule-based multi-persona trading desk roundtable
├── ai_synthesis.py        # Optional Gemini-powered roundtable (falls back to analysis.py)
├── watchlist.py           # TradingView watchlist import + symbol health scorer
├── notify.py              # Morning push report (Telegram/Discord, stdlib only)
├── daily_history.py       # One close snapshot per trading day (feeds delta + push)
├── forecast_log.py        # Prospective forecast log + next-session grading (docs/prospective-log.md)
├── eod_job.py             # Standalone EOD runner for launchd/cron (no server needed)
├── backtest.py            # Walk-forward replay: IC, decile, regime & strategy tests
├── backtest_report.py     # Offline Markdown report generator for backtest_results.csv
├── backtest_stats.py      # Pure offline stats: baselines, bootstrap CIs, costs
├── backtest_experiment.py # Scratchpad for weight/threshold experiments
├── config.py              # ← All user-tunable settings (port, TTLs, weights, WL thresholds)
├── config_local.py        # (git-ignored) your local secrets, e.g. GEMINI_API_KEY
├── models.py              # TypedDict schemas (Quote, PillarResult, DashboardResult)
├── should-i-trade-v6.html # Single-page dashboard shell
├── static/
│   ├── app.js             # Dashboard rendering (vanilla JS, no frameworks)
│   ├── app.css            # Terminal theme (dark + light), responsive ≥320px
│   └── app.test.js        # Vitest unit tests for the JS helpers
├── assets/logo.svg        # Project mark
├── watchlists/            # Drop TradingView .txt exports here
├── test_scoring.py        # Scoring pillar unit tests
├── test_data.py           # Data layer + circuit-breaker tests
├── test_analysis.py       # Roundtable persona tests
├── test_backtest_report.py # Backtest report generator tests
├── test_backtest_stats.py # Baseline/bootstrap/cost analytics tests
├── test_fixes.py          # Script-style infra regression suite (python3 test_fixes.py)
├── docs/
│   ├── backtest-methodology.md # Backtest design, assumptions, update protocol
│   └── backtest-report.md      # Generated human-readable replay report
├── .github/workflows/     # CI: Python 3.10–3.12 matrix + JS lint/tests
├── requirements.txt       # Notes only — core app needs no pip packages
└── history.json           # Auto-generated at runtime; score history for sparkline
```

Run the full Python suite with `python3 -m unittest discover` (test_fixes.py
is script-style and skips itself under discovery — run it directly as CI does).

---

## Architecture

```
Browser ──GET /──────────────────► server.py
                                       │
                          ┌────────────▼────────────┐
                          │  _DASHBOARD_CACHE (60s)  │
                          └────────────┬────────────┘
                                       │ cache miss
                          ┌────────────▼────────────┐
                          │     scoring.py           │
                          │  compute_dashboard()     │
                          │  ~7.4s, 33 symbols       │
                          └──┬───┬───┬───┬───┬──────┘
                             │   │   │   │   │
                           Vol Trd Brd Mom Mac
                             └───┴───┴───┴───┘
                              Weighted composite
                                     │
                          ┌──────────▼──────────┐
                          │     analysis.py      │
                          │    roundtable()      │
                          │  5 AI personas +     │
                          │  Desk Head synthesis │
                          └─────────────────────┘
```

Data flows: `data.py` fetches from Yahoo Finance (primary), falling back to Stooq (equities), CoinGecko (BTC), or Binance (BTC) as needed. All fetches happen in parallel using `ThreadPoolExecutor`.

---

## Scoring System

### Pillars & Weights

| Pillar | Weight | What it measures |
|---|---|---|
| **Trend** | 30% | SPY MA stack (20/50/200), RSI, MACD, ATR, volume confirmation |
| **Breadth** | 25% | Sector & industry advance/decline, RSP vs SPY, % sectors above 200d |
| **Momentum** | 20% | RSP/SPY relative strength, IWM leadership, sector RS rotation |
| **Volatility** | 15% | VIX level/trend/percentile, VIX term structure, VIX9D, SKEW, flow |
| **Macro** | 10% | 10Y yield, DXY, yield curve, HYG credit, BTC, GLD (FOMC/OpEx/seasonality shown as context, not scored — v6.1) |

> Weights are defined in `config.py` and can be adjusted without touching logic files.

> **Correlation note:** the five pillars are substantially correlated — the composite behaves like roughly three effective inputs, not five independent votes. Macro is the most independent pillar. Don't read the five bars as five separate confirmations.

### Risk-Posture Thresholds

The score is a conditions/exposure dial. The **engage line is 55** (the tested engagement threshold), not 70.

| Score | Posture | Conditions Band |
|---|---|---|
| ≥ 85 | **RISK-ON** 🟢 | Strongest — calm, broad, established uptrend |
| 70–84 | **CONSTRUCTIVE** 🟢 | Constructive — positive trend, supportive participation |
| 55–69 | **SELECTIVE** 🟡 | Mixed — internal signals disagree |
| 40–54 | **DE-RISK** 🟠 | Weak — choppy, elevated adverse-move risk |
| < 40 | **RISK-OFF** 🔴 | Stressed — descriptive only, not a timing signal |

Bands describe conditions; they do not size positions. The only exposure
percentage on the dashboard is the **volatility budget** below.

### Volatility Budget (illustrative)

```text
realized_annual_vol   = std(SPY daily returns, 20d) × sqrt(252)
SPY-equivalent expo.  = clamp(target_annual_vol / realized_annual_vol, 0, 100%)
```

The default target (~7.8% annual vol) is the backtest calibration — the
no-pillar baseline that beat the score rule on return, Sharpe, and max
drawdown (see [Backtest Report](docs/backtest-report.md)). You can pick a
different target in Settings (bounded presets; stored locally).

**Limitations:** SPY-only, trailing 20-day window, before costs, no
covariance with anything else you hold, no suitability assessment — an
illustrative market-level calculation, **not personalized advice**.

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /` | — | Serves `should-i-trade-v6.html` |
| `GET /api/dashboard` | — | Full scoring payload (JSON, cached 60s) |
| `GET /api/watchlist-health` | — | Watchlist symbol scores (cached 5min) |
| `GET /api/history-scores` | — | Rolling 12-hour score history |
| `GET /api/analysis` | — | Trading desk roundtable result |
| `GET /api/stream` | SSE | Server-sent dashboard refresh events |
| `GET /health` | — | Server uptime, cache state, history count |
| `GET /metrics` | — | Request/hit/miss/error counters |

### `/health` example response
```json
{
  "status": "ok",
  "uptime_seconds": 3721,
  "dashboard_cache_age_seconds": 14.2,
  "dashboard_cache_valid": true,
  "dashboard_ttl_seconds": 60,
  "history_snapshots": 48
}
```

### `/metrics` example response
```json
{
  "uptime_seconds": 3721,
  "requests": 412,
  "cache_hits": 398,
  "cache_misses": 14,
  "errors": 0
}
```

### Rate Limiting
All `/api/*` endpoints are rate-limited to **30 requests per minute per IP**.  
Exceeding the limit returns `HTTP 429 Too Many Requests`.  
Limits are configurable in `config.py` (`RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW`).

On proxied deployments (Render), every socket peer is the platform load
balancer, so the limiter keys on the first `X-Forwarded-For` hop (set by the
platform). Locally only the socket address is trusted, since a direct client
could forge that header. SSE connections are capped at `SSE_MAX_CLIENTS`
(default 32, HTTP 503 beyond that) with a bounded per-connection lifetime.

---

## Configuration

All user-tunable settings live in **`config.py`** — edit that file instead of touching logic code:

```python
# config.py

PORT           = 8765   # listening port
DASHBOARD_TTL  = 60     # seconds between full market-data refreshes
WATCHLIST_TTL  = 300    # seconds between watchlist recomputes
HISTORY_MAXLEN = 144    # max sparkline snapshots (~12 h at 5-min intervals)

RATE_LIMIT_MAX    = 30  # max API requests per IP per window
RATE_LIMIT_WINDOW = 60  # window in seconds

PILLAR_WEIGHTS = {      # must sum to 1.0
    "volatility": 0.15,
    "trend":      0.30,
    "breadth":    0.25,
    "momentum":   0.20,
    "macro":      0.10,
}
```

**Secrets stay out of git.** For machine-specific values (e.g. `GEMINI_API_KEY`
for the optional AI Desk Head), create a `config_local.py` next to `config.py`
— it is git-ignored and overrides any value in `config.py`:

```python
# config_local.py  (never committed)
GEMINI_API_KEY = "your-key-here"
```

The `GEMINI_API_KEY` environment variable still takes priority over both files.

---

## Daily Push Report

Every trading morning at **09:00 ET** the server can push a one-message
conditions report — score with delta vs yesterday's close, posture band (and
any band change), per-pillar deltas, data-quality state, and near-term
econ/FOMC events — to Telegram and/or Discord. A close snapshot is recorded
at **16:05 ET** each trading day (`daily_history.json`, git-ignored) and also
powers the "Since yesterday" strip on the dashboard.

**Disabled by default** — with no channel configured, nothing is sent and
nothing changes. Weekends and NYSE holidays are skipped automatically.

### Setup (~2 minutes)

**Telegram:** message [@BotFather](https://t.me/BotFather) → `/newbot` → copy
the token. Send your new bot any message, then open
`https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.

**Discord:** channel settings → Integrations → Webhooks → New Webhook → copy URL.

Put the values in git-ignored `config_local.py` (env vars take priority):

```python
# config_local.py  (never committed)
TELEGRAM_BOT_TOKEN = "123456:ABC..."
TELEGRAM_CHAT_ID   = "123456789"
# and/or
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
```

Test immediately (also usable from cron/launchd/CI — no server needed):

```bash
python3 notify.py    # prints the report; sends it if a channel is configured
```

Tuning in `config.py`: `PUSH_TIME_ET`, `EOD_SNAPSHOT_TIME_ET`,
`PUSH_ONLY_ON_BAND_CHANGE` (**default on**: pushes only when the posture band
changed vs the previous close — daily score wiggles below the historical
median move of ±14 pts are noise; set `False` for a push every morning),
`DASHBOARD_URL` (footer link). The public Render demo never pushes —
it has no secrets.

Displayed band labels use a small hysteresis (`BAND_HYSTERESIS_PTS`, default
3): a band flip takes effect once the score clears the boundary by that many
points, so a 54→55→54 wiggle doesn't churn DE-RISK↔SELECTIVE. The payload
always carries the un-sticky `natural_decision` alongside, and safety caps
bypass hysteresis.

---

## Data Sources

All sources are free and require no authentication:

- **Yahoo Finance v8 API** — primary source for all equity/ETF quotes and history
- **Stooq CSV** — fallback for equity data if Yahoo returns empty
- **CoinGecko API** — BTC price fallback
- **Binance public API** — BTC price secondary fallback

### Economic Calendar

Key US economic release dates (NFP, CPI, PPI, GDP) and FOMC meeting dates are stored in `data.py`.  
Current coverage: **through December 2027**.  
The server logs a `WARNING` automatically when coverage drops below 30 days — check logs if you see stale econ/FOMC data.  
Update `_ECON_CALENDAR` and `_FOMC_2026_2027` in `data.py` annually.

---

## Running Tests

```bash
python3 test_fixes.py    # infrastructure + security regression suite
python3 test_scoring.py  # scoring pillar unit tests (fully offline)
python3 test_data.py     # data-layer + circuit-breaker tests
python3 test_contracts.py # dashboard payload schema contract tests
python3 test_backtest_report.py # offline generated-report contract tests
python3 test_backtest_stats.py # baseline/bootstrap/cost analytics tests
python3 test_analysis.py # roundtable persona tests
npm test                 # frontend unit tests
```

CI runs Python tests on 3.10, 3.11, and 3.12, plus JS lint/tests on Node 20.

## Backtest Reporting

The historical replay is intentionally split into two steps:

```bash
python3 backtest.py        # networked replay; writes backtest_results.csv
python3 backtest_report.py # offline report; writes docs/backtest-report.md
```

Commit report updates only after checking that the methodology, README claims,
and generated report all tell the same story.

---

## Notes

- `history.json` is auto-created at runtime and excluded from version control (see `.gitignore`). It stores up to 144 snapshots (~12 hours at 5-minute intervals) for the sparkline chart.
- The server uses a `ThreadingHTTPServer` so parallel browser tabs don't each trigger separate full data fetches — the 60-second cache handles that.
- The roundtable analysis is fully rule-based (deterministic) — no LLM or external AI API is used.
- Path traversal is blocked at the file-serving layer: requests for any file outside the project directory return `403 Forbidden`.

---

## Author & License

Built by **Nueraili Abulizi** as a personal pre-session market quality tool.

Released under the [MIT License](LICENSE).
