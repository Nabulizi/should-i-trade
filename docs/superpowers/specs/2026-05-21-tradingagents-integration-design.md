# TradingAgents Integration Design

**Date:** 2026-05-21  
**Project:** should-i-trade  
**Status:** Approved

---

## Goals

1. **Replace the rule-based roundtable** in `analysis.py` with TradingAgents' LLM-powered multi-agent pipeline (Analysts → Researcher debate → Trader decision), running against SPY and QQQ.
2. **Add a project review CLI** (`review.py`) with three modes: methodology critique, signal comparison, and code review — all powered by Claude via TradingAgents' Anthropic backend.

---

## Dependencies

| Dependency | Purpose | Required key |
|---|---|---|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Multi-agent LLM trading framework | `ANTHROPIC_API_KEY` |
| Anthropic Claude | LLM backbone for all agents | `ANTHROPIC_API_KEY` |
| Alpha Vantage (free tier) | Fundamentals + news data for TradingAgents | `ALPHA_VANTAGE_API_KEY` |

Keys stored in `.env` at the project root (already gitignored).

---

## Architecture

### File Changes

```
should-i-trade/
├── analysis.py          ← CHANGED: LLM-powered roundtable with legacy fallback
├── analysis_legacy.py   ← NEW: copy of original rule-based roundtable
├── review.py            ← NEW: on-demand CLI review script
├── .env                 ← NEW: API keys (gitignored)
└── docs/superpowers/specs/
    └── 2026-05-21-tradingagents-integration-design.md  ← this file
```

TradingAgents is installed as a Python package via `pip install .` from a local clone (not committed to this repo).

### Two Independent Caches

| Cache | TTL | Contents |
|---|---|---|
| `_DASHBOARD_CACHE` (existing, 60s) | 60s | Scoring pillars, market data, decision badge |
| `_ROUNDTABLE_CACHE` (new, 1800s) | 30 min | TradingAgents multi-agent discussion text |

The roundtable cache has a much longer TTL because LLM calls are expensive and slow. The two caches are completely independent — a dashboard refresh never blocks on the roundtable.

---

## Goal 1: Roundtable Replacement

### Call Flow

```
GET /api/analysis
        │
        ▼
roundtable(dashboard_data)
        │
        ├─ _ROUNDTABLE_CACHE fresh? ──► return cached result immediately
        │
        └─ cache stale/empty
                │
                ├─ Return legacy rule-based output immediately (non-blocking)
                │
                └─ Spawn background thread:
                        │
                        ▼
              TradingAgentsGraph(anthropic_config)
              .propagate("SPY", today)
              .propagate("QQQ", today)
                        │
                        ▼
              Map agent outputs → 5 persona slots:
              ┌──────────────────┬────────────────────────────────────┐
              │ Persona (UI)     │ TradingAgents source               │
              ├──────────────────┼────────────────────────────────────┤
              │ Technician       │ Technical Analyst agent            │
              │ Macro Analyst    │ News + Fundamentals Analyst agents │
              │ Risk Manager     │ Researcher (bear side)             │
              │ Quant            │ Researcher (bull side)             │
              │ Desk Head        │ Trader agent final decision        │
              └──────────────────┴────────────────────────────────────┘
                        │
                        ▼
              Write to _ROUNDTABLE_CACHE (30 min TTL)
```

### Key Constraints

- **`roundtable()` is always non-blocking.** It returns immediately — either from cache or from the legacy fallback while the background thread runs.
- **Persona names are unchanged** in the output dict so the frontend (`should-i-trade-v5.html`) requires zero changes.
- **Fallback is transparent.** If TradingAgents fails (API error, missing key, timeout), the legacy rule-based output is returned and an error is logged. The dashboard never goes blank.
- **Config:** TradingAgents is configured with `llm_provider: "anthropic"`, `deep_think_llm: "claude-sonnet-4-5"`, `quick_think_llm: "claude-haiku-4-5"`, `max_debate_rounds: 1` (to keep latency manageable on free-tier Alpha Vantage).

### Error Handling

| Failure mode | Behavior |
|---|---|
| `ANTHROPIC_API_KEY` missing | Fall back to legacy permanently; log warning on startup |
| TradingAgents raises exception | Return last good cache or legacy fallback; log error |
| Alpha Vantage rate limit | TradingAgents retries internally; falls back if exhausted |
| Background thread timeout (>120s) | Thread is abandoned; cache not updated; legacy used |

---

## Goal 2: Review CLI (`review.py`)

### Usage

```bash
python3 review.py --methodology   # ~30s
python3 review.py --compare       # ~2-3 min (server must be running)
python3 review.py --code          # ~60s
python3 review.py --all           # all three; saves docs/reviews/YYYY-MM-DD-review.md
```

### Mode: `--methodology`

Reads `config.py` (pillar weights) and the top-level docstrings + scoring logic from `scoring.py`. Sends to Claude with a structured prompt asking for critique of:
- Pillar design and coverage gaps
- Weight appropriateness
- Edge cases and market regimes not captured
- Blind spots in the decision thresholds

Prints a structured report (Markdown) to stdout.

### Mode: `--compare`

1. Runs `TradingAgentsGraph.propagate("SPY", today)` and `propagate("QQQ", today)`
2. Fetches `http://localhost:8765/api/dashboard` for current score + decision
3. Sends both results to Claude with prompt: *"Reconcile these two market assessments. Where do they agree? Where do they diverge, and what might explain the difference?"*
4. Prints a side-by-side table + reconciliation note

**Requires:** server running at `localhost:8765`.

### Mode: `--code`

Reads `scoring.py`, `analysis.py`, `data.py`, `watchlist.py` in full. Sends to Claude with prompt: *"Review this trading dashboard codebase. Focus on logic errors, scoring methodology flaws, data quality risks, and maintainability. Group findings by severity: Critical / Warning / Suggestion."*

Prints findings to stdout.

### Output

- All modes: structured Markdown printed to stdout
- `--all`: also saves to `docs/reviews/YYYY-MM-DD-HH-MM-review.md`

---

## Installation Steps (Implementation Phase)

1. Clone TradingAgents to a sibling directory (not inside this repo)
2. `pip install .` from TradingAgents directory
3. Create `.env` with `ANTHROPIC_API_KEY` and `ALPHA_VANTAGE_API_KEY`
4. Copy `analysis.py` → `analysis_legacy.py`
5. Rewrite `analysis.py` with new caching + background thread + TradingAgents calls
6. Write `review.py`
7. Run `python3 test_fixes.py` and `python3 test_scoring.py` to confirm nothing broke

---

## Out of Scope

- Wiring TradingAgents into the scoring pillars (pillars remain rule-based)
- Automated scheduled runs of `review.py`
- Storing TradingAgents decision history in `history.json`
- Any frontend changes
