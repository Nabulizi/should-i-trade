# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Python (backend)
```bash
# Run the server (dev)
python3 server.py

# Run all Python tests
python3 test_fixes.py && python3 test_scoring.py && python3 test_data.py && python3 test_contracts.py && python3 test_backtest_report.py && python3 test_analysis.py && python3 test_smoke.py

# Run a single test file
python3 test_scoring.py

# Syntax check all Python files
python -m py_compile server.py scoring.py data.py analysis.py ai_synthesis.py watchlist.py models.py backtest_report.py
```

### JavaScript (frontend)
```bash
npm ci            # install dev deps
npm test          # run Vitest unit tests (static/app.test.js)
npm run lint      # ESLint on static/app.js
```

### CI matrix
GitHub Actions runs Python tests on 3.10/3.11/3.12, JS tests on Python 3.12 + Node 20.

## Architecture

The app is a single-page market quality dashboard that answers "Should I trade today?" It has no third-party Python dependencies (stdlib only). Gemini AI integration is optional.

```
Browser
  └─ should-i-trade-v6.html + static/app.js (vanilla JS, SSE-driven)
       ↕ HTTP/SSE
server.py (ThreadingHTTPServer, port 8765)
  ├─ /api/dashboard   → scoring.compute_dashboard()   [60s cache]
  ├─ /api/analysis    → analysis.roundtable() or ai_synthesis (Gemini)
  ├─ /api/watchlist-health → watchlist.compute_watchlist_health() [5min cache]
  ├─ /api/stream      → SSE broadcast of score updates
  └─ /health, /metrics
       ↕
data.py   Yahoo Finance v8 (primary) → Stooq CSV → CoinGecko/Binance (BTC fallback)
scoring.py  5-pillar engine: trend(30%) breadth(25%) momentum(20%) volatility(15%) macro(10%)
analysis.py  5 rule-based personas + Desk Head synthesis
ai_synthesis.py  optional Gemini 2.5 Flash version of each persona
watchlist.py  TradingView-format watchlist health scoring
```

### Key modules

| File | Role |
|---|---|
| `server.py` | HTTP routing, rate limiting (30 req/min/IP), caching, SSE broadcast |
| `scoring.py` | Deterministic 5-pillar engine; returns `PillarResult` TypedDicts |
| `data.py` | Parallel symbol fetches (ThreadPoolExecutor), circuit breaker per symbol |
| `analysis.py` | Rule-based trading desk personas |
| `ai_synthesis.py` | Gemini 2.5 Flash persona chain (graceful fallback to rule-based) |
| `config.py` | All user-tunable settings: weights, TTLs, rate limits, API keys |
| `models.py` | `Quote`, `PillarResult`, `DashboardResult` TypedDicts |

### Scoring pillars
- **Trend** (30%): SPY MA stack (20/50/200), RSI, MACD, ATR, tape character
- **Breadth** (25%): Sector advance/decline, RSP vs SPY, % sectors above 200-day
- **Momentum** (20%): RSP/SPY relative strength, IWM leadership, sector rotation
- **Volatility** (15%): VIX level/trend/percentile, term structure (VIX9D/VIX3M), SKEW, option flow
- **Macro** (10%): 10Y yield, DXY, yield curve, HYG credit, BTC, GLD, FOMC proximity

Decision thresholds: ≥85 STRONG YES → 70 YES → 55 CAUTION → 40 NO → <40 WAIT.

### Caching & reliability patterns
- Thread-safe global caches with locks; stale-while-revalidate background refresh
- Per-symbol circuit breaker (opens after 3 failures, resets after 60s)
- Rate limiting uses sliding-window per-IP buckets (configurable in `config.py`)

### Configuration
All tunables live in `config.py`: `PORT`, `DASHBOARD_TTL`, `WATCHLIST_TTL`, `PILLAR_WEIGHTS`, `GEMINI_API_KEY`, circuit breaker settings, and more. Production overrides `PORT` and detects Render.com via `RENDER` env var.

### Deployment
Render.com free tier (`render.yaml`); Python 3.11; auto-deploys on push to `main`. CORS allows all origins in production, restricts to localhost in dev.
