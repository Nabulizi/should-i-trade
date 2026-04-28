# Should I Trade? — Market Quality Terminal v5

A single-page, self-hosted dashboard that answers one question before every trading session: **is the market environment good enough to trade actively?**

No subscriptions, no API keys, no cloud dependencies — all data comes from free public sources.

---

## Screenshot

> Live dashboard running at `http://localhost:8765`

The dashboard shows a composite **Market Quality Score (0–100)**, five scoring pillars, a trading decision recommendation, and a multi-persona AI roundtable discussion — all updated automatically every 60 seconds.

---

## Features

| Feature | Detail |
|---|---|
| **Market Quality Score** | 0–100 composite score across 5 weighted pillars |
| **5-Pillar Breakdown** | Volatility · Trend · Breadth · Momentum · Macro |
| **Decision Badge** | GO / CAUTION / WAIT — clear session recommendation |
| **Trading Desk Roundtable** | 5 rule-based AI personas (Technician, Macro, Risk, Quant, Desk Head) |
| **Score Sparkline** | 12-hour rolling history chart with persistent storage |
| **Economic Calendar** | FOMC & key econ event proximity alerts |
| **Sector Heatmap** | All 11 SPDR sectors + 9 industry subsector ETFs |
| **Market Conditions** | SPY, QQQ, VIX, VIX3M, HYG, GLD, DXY, TLT, 10Y yield, BTC |
| **Responsive UI** | Works on laptop screens down to ~600px wide |
| **Zero API keys** | Yahoo Finance → Stooq → CoinGecko → Binance (all free) |

---

## Quick Start

### Requirements
- Python 3.9+
- No third-party packages (standard library only)

### Run
```bash
git clone git@github.com:Nabulizi/should-i-trade.git
cd should-i-trade
python3 server.py
```

Then open **http://localhost:8765** in your browser. The first load takes ~7–8 seconds as it fetches live data for 33 symbols in parallel.

> The server auto-opens the browser on startup. Re-open manually if needed.

---

## Project Structure

```
should-i-trade/
├── server.py              # HTTP server, request routing, caching, history persistence
├── scoring.py             # 5-pillar scoring engine (0–100 per pillar, weighted composite)
├── data.py                # Market data fetchers (Yahoo Finance + fallbacks)
├── analysis.py            # Rule-based multi-persona trading desk roundtable
├── should-i-trade-v5.html # Single-page dashboard UI (vanilla JS, no frameworks)
├── requirements.txt       # Notes only — no pip packages required
└── history.json           # Auto-generated at runtime; score history for sparkline
```

---

## Architecture

```
Browser ──GET /──────────────────► server.py
                                       │
                          ┌────────────▼────────────┐
                          │   _DASHBOARD_CACHE (60s) │
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
| **Trend** | 25% | SPY MA stack (20/50/200), RSI, ATH distance, regime |
| **Breadth** | 20% | Sector & industry advance/decline ratio, RSP vs SPY |
| **Volatility** | 20% | VIX level, VIX term structure (VIX vs VIX3M), regime percentile |
| **Momentum** | 20% | TQQQ/SQQQ ratio, leveraged ETF signals, QQQ relative strength |
| **Macro** | 15% | HYG credit, 10Y yield, DXY, GLD, BTC risk-on/off signals |

### Decision Thresholds

| Score | Decision | Meaning |
|---|---|---|
| ≥ 65 | **GO** 🟢 | Market conditions support active trading |
| 45–64 | **CAUTION** 🟡 | Trade small, be selective |
| < 45 | **WAIT** 🔴 | Stay flat or reduce exposure |

---

## Data Sources

All sources are free and require no authentication:

- **Yahoo Finance v8 API** — primary source for all equity/ETF quotes and history
- **Stooq CSV** — fallback for equity data if Yahoo returns empty
- **CoinGecko API** — BTC price fallback
- **Binance public API** — BTC price secondary fallback

---

## Configuration

Key constants are near the top of each file:

**`server.py`**
```python
PORT = 8765           # Change listening port
_DASHBOARD_TTL = 60   # Cache TTL in seconds (refresh rate)
```

**`scoring.py`**
```python
PILLAR_WEIGHTS = {    # Adjust pillar weights (must sum to 1.0)
    "volatility": 0.20,
    "trend":      0.25,
    "breadth":    0.20,
    "momentum":   0.20,
    "macro":      0.15,
}
```

---

## Notes

- `history.json` is auto-created at runtime and excluded from version control (see `.gitignore`). It stores up to 144 snapshots (~12 hours at 5-minute intervals) for the sparkline chart.
- The server uses a `ThreadingHTTPServer` so parallel browser tabs don't each trigger separate full data fetches — the 60-second cache handles that.
- The roundtable analysis is fully rule-based (deterministic) — no LLM or external AI API is used.

---

## Author

Built by **Nueraili Abulizi** as a personal pre-session market quality tool.
