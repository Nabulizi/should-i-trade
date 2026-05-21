# TradingAgents Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install TradingAgents and wire it into should-i-trade: replace the rule-based roundtable in `analysis.py` with real LLM agents, and add a `review.py` CLI for on-demand project review (methodology critique, signal comparison, code review).

**Architecture:** `analysis.py` gets a 30-min cache + background thread; `roundtable()` stays non-blocking by returning legacy output while TradingAgents runs in the background. `review.py` is a standalone CLI that uses Anthropic directly for methodology/code review and TradingAgents for signal comparison. All work happens on branch `feat/tradingagents-integration`.

**Tech Stack:** Python 3.10+, TradingAgents v0.2.5 (LangGraph-based), Anthropic Claude (`claude-sonnet-4-5` / `claude-haiku-4-5`), Alpha Vantage free tier, `anthropic` Python package.

---

## File Map

| File | Change |
|---|---|
| `.gitignore` | Add `.env` |
| `analysis_legacy.py` | NEW — verbatim copy of current `analysis.py` |
| `analysis.py` | REWRITE — non-blocking cache + background TradingAgents thread |
| `test_analysis_new.py` | NEW — contract tests for new `analysis.py` |
| `review.py` | NEW — CLI: `--methodology`, `--compare`, `--code`, `--all` |
| `.env` | NEW — API keys (not committed) |
| `docs/reviews/` | NEW directory — `--all` output saved here |

---

### Task 1: Setup — Gitignore, TradingAgents Install, .env

**Files:**
- Modify: `.gitignore`
- Create: `.env` (from template — not committed)

- [ ] **Step 1: Add `.env` to `.gitignore`**

Open `.gitignore` and append these two lines at the end:
```
# API keys
.env
```

- [ ] **Step 2: Clone TradingAgents alongside this repo and install**

```bash
cd ~/Documents   # same parent directory as should-i-trade
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
pip install .
cd ../Trade   # back to should-i-trade
```

Expected: `Successfully installed tradingagents-0.2.x` (version may vary).

- [ ] **Step 3: Create `.env` with your API keys**

```bash
cat > .env << 'EOF'
ANTHROPIC_API_KEY=your_anthropic_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
EOF
```

Replace the placeholder values with your real keys. Verify the file is gitignored:
```bash
git status
```
Expected: `.env` does NOT appear in the output.

- [ ] **Step 4: Verify TradingAgents installed correctly**

```bash
python3 -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Verify anthropic package is installed (TradingAgents installs it)**

```bash
python3 -c "import anthropic; print('anthropic', anthropic.__version__)"
```

Expected: `anthropic 0.x.x`

- [ ] **Step 6: Commit gitignore change**

```bash
git add .gitignore
git commit -m "chore: add .env to .gitignore for API key safety"
```

---

### Task 2: Back Up `analysis.py` → `analysis_legacy.py`

**Files:**
- Create: `analysis_legacy.py`

- [ ] **Step 1: Copy analysis.py to analysis_legacy.py**

```bash
cp analysis.py analysis_legacy.py
```

- [ ] **Step 2: Verify the copy imports cleanly**

```bash
python3 -c "from analysis_legacy import roundtable; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify legacy roundtable still returns correct schema**

```bash
python3 -c "
from analysis_legacy import roundtable
d = {
  'score': 65, 'decision': 'YES',
  'pillars': {
    'trend': {'score': 70, 'details': {'above_20': True, 'above_50': True, 'above_200': True,
      'regime': 'Bull', 'ath_dist': -3.0, 'rsi14': 55, 'spy_change_pct': 0.5,
      'macd_hist': 0.02, 'macd_label': 'Bullish (above 0)', 'char_label': 'Trending', 'vol_confirm': True}},
    'macro': {'score': 60, 'details': {'tnx_value': 4.2, 'yield_direction': 'Falling',
      'yield_label': 'Neutral', 'dxy_label': 'Weakening', 'dxy_change_pct': -0.3,
      'btc_trend': 'Up', 'btc_from_high': -10.0, 'fomc_days': 20, 'fomc_date': '2026-06-10',
      'hyg_label': 'Risk-On', 'gld_trend': 'Flat', 'gld_label': 'Neutral',
      'curve_spread': 0.1, 'curve_label': 'Flat'}},
    'volatility': {'score': 68, 'details': {'vix_value': 18.0, 'vix_label': 'Elevated',
      'vix_percentile': 55, 'vix_trend': 'Falling', 'term_slope': 1.2, 'skew_value': 130,
      'skew_label': 'Moderate', 'vix9d_value': 16.0, 'vix_flow': 'Mixed'}},
    'breadth': {'score': 65, 'details': {'adv_dec_ratio': 1.8, 'rsp_spy_ratio': 0.02,
      'sectors_above_200d': 7, 'sector_adv_dec': 8}},
    'momentum': {'score': 63, 'details': {'rsp_spy_rs': 0.01, 'iwm_spy_rs': -0.005,
      'qqq_spy_rs': 0.03, 'sector_rotation': 'Risk-On'}},
  },
  'conditions': {'SPY': {'price': 555.0, 'change_pct': 0.5}},
  'watchlist': [], 'econ': {'fomc_days': 20, 'fomc_date': '2026-06-10'},
}
r = roundtable(d)
print('personas:', len(r['personas']), '| keys:', list(r.keys()))
"
```

Expected: `personas: 5 | keys: ['personas', 'timestamp']`

- [ ] **Step 4: Commit**

```bash
git add analysis_legacy.py
git commit -m "chore: backup rule-based roundtable as analysis_legacy.py"
```

---

### Task 3: Write Failing Tests for New `analysis.py`

**Files:**
- Create: `test_analysis_new.py`

- [ ] **Step 1: Write the test file**

Create `test_analysis_new.py` with this exact content:

```python
"""
Contract tests for the new analysis.py.

These tests verify that roundtable() always:
  1. Returns the correct schema (5 personas, all required keys)
  2. Returns in < 1 second (non-blocking)
  3. Falls back to legacy when ANTHROPIC_API_KEY is missing
  4. Returns the cached object when cache is fresh
"""
from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

# Minimal dashboard snapshot — enough to feed all legacy persona functions.
_DASHBOARD = {
    "score": 65,
    "decision": "YES",
    "pillars": {
        "trend": {
            "score": 70,
            "details": {
                "above_20": True, "above_50": True, "above_200": True,
                "regime": "Bull", "ath_dist": -3.0, "rsi14": 55,
                "spy_change_pct": 0.5, "macd_hist": 0.02,
                "macd_label": "Bullish (above 0)", "char_label": "Trending",
                "vol_confirm": True,
            },
        },
        "macro": {
            "score": 60,
            "details": {
                "tnx_value": 4.2, "yield_direction": "Falling",
                "yield_label": "Neutral", "dxy_label": "Weakening",
                "dxy_change_pct": -0.3, "btc_trend": "Up",
                "btc_from_high": -10.0, "fomc_days": 20,
                "fomc_date": "2026-06-10", "hyg_label": "Risk-On",
                "gld_trend": "Flat", "gld_label": "Neutral",
                "curve_spread": 0.1, "curve_label": "Flat",
            },
        },
        "volatility": {
            "score": 68,
            "details": {
                "vix_value": 18.0, "vix_label": "Elevated",
                "vix_percentile": 55, "vix_trend": "Falling",
                "term_slope": 1.2, "skew_value": 130,
                "skew_label": "Moderate", "vix9d_value": 16.0,
                "vix_flow": "Mixed",
            },
        },
        "breadth": {
            "score": 65,
            "details": {
                "adv_dec_ratio": 1.8, "rsp_spy_ratio": 0.02,
                "sectors_above_200d": 7, "sector_adv_dec": 8,
            },
        },
        "momentum": {
            "score": 63,
            "details": {
                "rsp_spy_rs": 0.01, "iwm_spy_rs": -0.005,
                "qqq_spy_rs": 0.03, "sector_rotation": "Risk-On",
            },
        },
    },
    "conditions": {"SPY": {"price": 555.0, "change_pct": 0.5}},
    "watchlist": [],
    "econ": {"fomc_days": 20, "fomc_date": "2026-06-10"},
}

_REQUIRED_PERSONA_KEYS = {
    "persona", "role", "avatar", "stance", "stance_color", "read", "points", "verdict"
}


class TestRoundtableContract(unittest.TestCase):
    def setUp(self):
        import analysis
        analysis._ROUNDTABLE_CACHE["ts"] = 0.0
        analysis._ROUNDTABLE_CACHE["data"] = None
        analysis._REFRESH_RUNNING.clear()

    def test_returns_personas_and_timestamp(self):
        """roundtable() must always return personas list and timestamp."""
        import analysis
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = analysis.roundtable(_DASHBOARD)
        self.assertIn("personas", result)
        self.assertIn("timestamp", result)

    def test_returns_five_personas(self):
        """roundtable() must return exactly 5 personas."""
        import analysis
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = analysis.roundtable(_DASHBOARD)
        self.assertEqual(len(result["personas"]), 5)

    def test_each_persona_has_required_keys(self):
        """Each persona dict must have all required display keys."""
        import analysis
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = analysis.roundtable(_DASHBOARD)
        for persona in result["personas"]:
            missing = _REQUIRED_PERSONA_KEYS - persona.keys()
            self.assertFalse(missing, f"Persona '{persona.get('persona')}' missing: {missing}")

    def test_non_blocking_without_api_key(self):
        """roundtable() must return in < 1s when ANTHROPIC_API_KEY is absent."""
        import analysis
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            start = time.time()
            analysis.roundtable(_DASHBOARD)
            elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f"roundtable() blocked for {elapsed:.2f}s")

    def test_fallback_when_no_api_key(self):
        """roundtable() must fall back to legacy (no 'source' key) when key absent."""
        import analysis
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = analysis.roundtable(_DASHBOARD)
        # Legacy roundtable does not set "source"; TradingAgents output does.
        self.assertNotEqual(result.get("source"), "tradingagents")

    def test_cache_hit_returns_same_object(self):
        """roundtable() must return the cached object directly when cache is fresh."""
        import analysis
        cached = {
            "personas": [
                {"persona": "Cached", "role": "", "avatar": "",
                 "stance": "Bullish", "stance_color": "green",
                 "read": "cached read", "points": [], "verdict": "cached"}
            ] * 5,
            "timestamp": "12:00 UTC",
            "source": "tradingagents",
        }
        analysis._ROUNDTABLE_CACHE["ts"] = time.time()
        analysis._ROUNDTABLE_CACHE["data"] = cached
        result = analysis.roundtable(_DASHBOARD)
        self.assertIs(result, cached)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — all should FAIL**

```bash
python3 -m pytest test_analysis_new.py -v
```

Expected: Multiple failures — the current `analysis.py` doesn't have `_ROUNDTABLE_CACHE` or `_REFRESH_RUNNING`.

- [ ] **Step 3: Commit failing tests**

```bash
git add test_analysis_new.py
git commit -m "test: add contract tests for new analysis.py (currently failing)"
```

---

### Task 4: Rewrite `analysis.py`

**Files:**
- Modify: `analysis.py` (full rewrite)

- [ ] **Step 1: Replace the entire contents of `analysis.py`**

```python
"""
analysis.py — Trading Desk Roundtable (LLM-powered with legacy fallback)

On each call, roundtable() checks a 30-minute cache. If stale, it:
  1. Returns the last cached result (or legacy rule-based output if cache is empty)
  2. Spawns a background thread to refresh via TradingAgents on SPY + QQQ

If ANTHROPIC_API_KEY is not set, or TradingAgents fails for any reason,
the legacy rule-based output (analysis_legacy.py) is used transparently.
The dashboard never goes blank.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from analysis_legacy import roundtable as _legacy_roundtable

logger = logging.getLogger(__name__)

ROUNDTABLE_TTL = 1800  # 30 minutes

_ROUNDTABLE_CACHE: dict = {"ts": 0.0, "data": None}
_ROUNDTABLE_LOCK = threading.Lock()
_REFRESH_RUNNING = threading.Event()


def _is_cache_fresh() -> bool:
    return (time.time() - _ROUNDTABLE_CACHE["ts"]) < ROUNDTABLE_TTL


def _text(val: object, max_chars: int = 600) -> str:
    """Safely convert any value to a truncated string."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val[:max_chars]
    return str(val)[:max_chars]


def _map_ta_to_personas(state: dict, spy_decision: object, qqq_decision: object, legacy: dict) -> dict:
    """
    Map TradingAgents propagate() output onto the 5 existing persona slots.

    TradingAgents state keys (common across v0.2.x):
      state.get("market_report")              — technical + fundamental summary
      state.get("sentiment_report")           — sentiment analysis
      state.get("news_report")                — news analysis
      state.get("fundamentals_report")        — fundamentals analysis
      state.get("investment_debate_state", {})
        .get("bear_argument")                 — bear researcher text
        .get("bull_argument")                 — bull researcher text
      state.get("trader_investment_plan")     — trader's plan

    If a key is missing, the corresponding legacy persona's read is preserved.
    Run Task 5 first to confirm these key names against your installed version.
    """
    debate = state.get("investment_debate_state") or {}

    spy_str = _text(spy_decision)
    qqq_str = _text(qqq_decision)
    desk_summary = f"SPY: {spy_str}\n\nQQQ: {qqq_str}" if (spy_str or qqq_str) else None

    personas = [dict(p) for p in legacy["personas"]]  # shallow copy of each persona dict

    # 0 — Technician ← SPY market/technical report
    tech_text = _text(state.get("market_report") or state.get("technical_report"))
    if tech_text:
        personas[0]["read"] = tech_text

    # 1 — Macro Analyst ← news + fundamentals
    macro_parts = [
        _text(state.get("fundamentals_report")),
        _text(state.get("news_report")),
    ]
    macro_text = "\n\n".join(p for p in macro_parts if p)
    if macro_text:
        personas[1]["read"] = macro_text

    # 2 — Risk Manager ← bear researcher argument
    bear_text = _text(debate.get("bear_argument") or state.get("bear_researcher_report"))
    if bear_text:
        personas[2]["read"] = bear_text

    # 3 — Rotator/Quant ← bull researcher argument
    bull_text = _text(debate.get("bull_argument") or state.get("bull_researcher_report"))
    if bull_text:
        personas[3]["read"] = bull_text

    # 4 — Desk Head ← trader plan or combined SPY/QQQ decision
    plan_text = _text(state.get("trader_investment_plan") or desk_summary)
    if plan_text:
        personas[4]["read"] = plan_text
        personas[4]["verdict"] = _text(spy_decision, 200) or personas[4]["verdict"]

    return {
        "personas": personas,
        "timestamp": time.strftime("%H:%M UTC", time.gmtime()),
        "source": "tradingagents",
    }


def _run_tradingagents(dashboard: dict, legacy: dict) -> None:
    """Background thread body: call TradingAgents on SPY + QQQ, update cache."""
    result = legacy  # default — overwritten on success
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "anthropic"
        config["deep_think_llm"] = "claude-sonnet-4-5"
        config["quick_think_llm"] = "claude-haiku-4-5"
        config["max_debate_rounds"] = 1

        today = time.strftime("%Y-%m-%d")
        ta = TradingAgentsGraph(debug=False, config=config)

        spy_state, spy_decision = ta.propagate("SPY", today)
        _, qqq_decision = ta.propagate("QQQ", today)

        result = _map_ta_to_personas(spy_state, spy_decision, qqq_decision, legacy)
        logger.info("Roundtable: TradingAgents refresh complete (source=tradingagents)")

    except ImportError:
        logger.warning("Roundtable: tradingagents package not installed — using legacy")
    except Exception as exc:
        logger.error("Roundtable: TradingAgents error (%s) — using legacy fallback", exc)
    finally:
        with _ROUNDTABLE_LOCK:
            _ROUNDTABLE_CACHE["ts"] = time.time()
            _ROUNDTABLE_CACHE["data"] = result
        _REFRESH_RUNNING.clear()


def _maybe_refresh(dashboard: dict, legacy: dict) -> None:
    """Spawn the background refresh thread if one isn't already running."""
    if _REFRESH_RUNNING.is_set():
        return
    _REFRESH_RUNNING.set()
    t = threading.Thread(target=_run_tradingagents, args=(dashboard, legacy), daemon=True)
    t.start()


def roundtable(dashboard: dict) -> dict:
    """
    Full trading desk output. Always non-blocking.

    Returns cached TradingAgents result if fresh. Otherwise triggers a
    background refresh and returns the last cached result (or legacy fallback)
    immediately.
    """
    with _ROUNDTABLE_LOCK:
        if _is_cache_fresh() and _ROUNDTABLE_CACHE["data"] is not None:
            return _ROUNDTABLE_CACHE["data"]
        stale = _ROUNDTABLE_CACHE["data"]

    # No API key → fall back to legacy permanently, no threads
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — using rule-based roundtable")
        return _legacy_roundtable(dashboard)

    legacy = _legacy_roundtable(dashboard)
    _maybe_refresh(dashboard, legacy)
    return stale if stale is not None else legacy
```

- [ ] **Step 2: Run contract tests — all should PASS**

```bash
python3 -m pytest test_analysis_new.py -v
```

Expected:
```
test_analysis_new.py::TestRoundtableContract::test_cache_hit_returns_same_object PASSED
test_analysis_new.py::TestRoundtableContract::test_each_persona_has_required_keys PASSED
test_analysis_new.py::TestRoundtableContract::test_fallback_when_no_api_key PASSED
test_analysis_new.py::TestRoundtableContract::test_non_blocking_without_api_key PASSED
test_analysis_new.py::TestRoundtableContract::test_returns_five_personas PASSED
test_analysis_new.py::TestRoundtableContract::test_returns_personas_and_timestamp PASSED
6 passed
```

- [ ] **Step 3: Run existing test suites**

```bash
python3 test_fixes.py && python3 test_scoring.py
```

Expected: same pass counts as before (48 assertions in test_fixes.py, 75 in test_scoring.py). Any failures here mean the rewrite broke something — stop and investigate.

- [ ] **Step 4: Commit**

```bash
git add analysis.py
git commit -m "feat: replace rule-based roundtable with TradingAgents LLM pipeline

- 30-min roundtable cache independent of 60s dashboard cache
- Non-blocking: returns legacy output while background thread runs
- Falls back to legacy on missing API key or any TradingAgents error
- Preserves exact persona schema — zero frontend changes required"
```

---

### Task 5: Verify TradingAgents Output Format (Live Probe)

This task confirms the actual state key names from `ta.propagate()` so the mapper in `_map_ta_to_personas` is accurate.

**Files:**
- Create (temp): `_ta_probe.py` — deleted after this task

- [ ] **Step 1: Load your API keys into the shell**

```bash
export $(grep -v '^#' .env | xargs)
```

- [ ] **Step 2: Create probe script**

```python
# _ta_probe.py — run once to inspect TradingAgents output format, then delete
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import time

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-haiku-4-5"   # cheapest model for probing
config["quick_think_llm"] = "claude-haiku-4-5"
config["max_debate_rounds"] = 1

ta = TradingAgentsGraph(debug=False, config=config)
today = time.strftime("%Y-%m-%d")

print(f"Running propagate('SPY', '{today}') — takes 2-5 minutes...")
state, decision = ta.propagate("SPY", today)

print("\n=== STATE KEYS ===")
print(list(state.keys()))

print("\n=== DECISION TYPE + VALUE (first 300 chars) ===")
print(type(decision).__name__, ":", str(decision)[:300])

for key in [
    "market_report", "technical_report", "sentiment_report",
    "news_report", "fundamentals_report", "investment_debate_state",
    "trader_investment_plan", "bear_researcher_report", "bull_researcher_report",
]:
    val = state.get(key)
    if val is not None:
        preview = str(val)[:150] if not isinstance(val, dict) else str(list(val.keys()))
        print(f"\n=== {key} (found) ===\n{preview}")
    else:
        print(f"\n--- {key}: NOT FOUND ---")
```

- [ ] **Step 3: Run probe (takes 2–5 minutes)**

```bash
python3 _ta_probe.py 2>&1 | tee /tmp/ta_probe_output.txt
```

- [ ] **Step 4: Review output and tune the mapper if needed**

Open `/tmp/ta_probe_output.txt`. Check which keys are present.

**If key names differ from what `_map_ta_to_personas` expects**, open `analysis.py` and update the relevant `state.get(...)` lines in `_map_ta_to_personas`:

| If actual key is... | Replace `state.get("market_report")` with... |
|---|---|
| `"technical_analyst_report"` | `state.get("technical_analyst_report")` |
| `"technical_analysis"` | `state.get("technical_analysis")` |

Apply the same pattern for each mismatched key. Then re-run:

```bash
python3 -m pytest test_analysis_new.py -v
```

Expected: still 6 passed.

- [ ] **Step 5: Clean up probe, commit if any mapper changes were made**

```bash
rm _ta_probe.py

# Only if you changed analysis.py in step 4:
git add analysis.py
git commit -m "fix: tune TradingAgents state key names from probe results"
```

---

### Task 6: Write `review.py`

**Files:**
- Create: `review.py`

- [ ] **Step 1: Create `review.py`**

```python
#!/usr/bin/env python3
"""
review.py — On-demand project review powered by Anthropic Claude.

Usage:
    python3 review.py --methodology   # Critique 5-pillar scoring design (~30s)
    python3 review.py --compare       # TradingAgents vs your score (~3 min, server must run)
    python3 review.py --code          # Code/logic review of key source files (~60s)
    python3 review.py --all           # All three; saves docs/reviews/YYYY-MM-DD-HH-MM-review.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent


def _load_dotenv() -> None:
    """Load .env file into os.environ (values already set in env take precedence)."""
    env_file = _SCRIPT_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        sys.exit(
            f"ERROR: {key} not set.\n"
            f"Add it to .env and run:  export $(grep -v '^#' .env | xargs)"
        )
    return val


def _ask_claude(prompt: str, system: str = "") -> str:
    """Call Anthropic Claude API and return the response text."""
    import anthropic
    client = anthropic.Anthropic(api_key=_require_env("ANTHROPIC_API_KEY"))
    kwargs: dict = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text


def _read_file(relative_path: str) -> str:
    return (_SCRIPT_DIR / relative_path).read_text(encoding="utf-8")


# ─── Mode 1: Methodology Review ────────────────────────────────────────────

def run_methodology_review() -> str:
    print("📐 Running methodology review...", flush=True)
    config_src = _read_file("config.py")
    scoring_src = _read_file("scoring.py")

    prompt = f"""You are a professional quantitative analyst reviewing a retail trading dashboard.

Below is the configuration (pillar weights) and the full scoring engine source.

== config.py ==
{config_src}

== scoring.py (first 8000 chars) ==
{scoring_src[:8000]}

Please critique this 5-pillar market quality scoring system. Structure your review as:

## 1. Pillar Design
- Are the 5 pillars (Volatility, Trend, Breadth, Momentum, Macro) the right dimensions?
- What important market dynamics are not captured?

## 2. Weight Assessment
- Are the weights (Trend 30%, Breadth 25%, Momentum 20%, Volatility 15%, Macro 10%) appropriate?
- Which single weight would you change and why?

## 3. Edge Cases & Blind Spots
- Which market regimes (flash crash, slow grind, options expiry, Fed day) might fool this system?
- Which specific scoring logic could produce false signals?

## 4. Decision Thresholds
- Are the 5 tiers (STRONG YES ≥85, YES 70–84, CAUTION 55–69, NO 40–54, WAIT <40) well-calibrated?
- Suggested improvements?

## 5. Summary Verdict
One paragraph: overall quality of this system and the single highest-value improvement."""

    result = _ask_claude(prompt)
    header = f"# Methodology Review\n_Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    return header + result


# ─── Mode 2: Signal Comparison ─────────────────────────────────────────────

def run_compare() -> str:
    print("🔄 Running signal comparison (takes 2–3 minutes)...", flush=True)

    # Fetch your dashboard score
    try:
        with urllib.request.urlopen("http://localhost:8765/api/dashboard", timeout=10) as resp:
            dashboard = json.loads(resp.read())
    except Exception as exc:
        sys.exit(
            f"ERROR: Could not reach http://localhost:8765/api/dashboard\n"
            f"Start the server first: python3 server.py\nDetails: {exc}"
        )

    your_score = dashboard.get("score")
    your_decision = dashboard.get("decision")
    pillar_scores = {k: v["score"] for k, v in dashboard.get("pillars", {}).items()}

    # Run TradingAgents on SPY and QQQ
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
    except ImportError:
        sys.exit(
            "ERROR: tradingagents not installed.\n"
            "Run: cd ~/Documents/TradingAgents && pip install ."
        )

    _require_env("ANTHROPIC_API_KEY")
    _require_env("ALPHA_VANTAGE_API_KEY")

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "anthropic"
    config["deep_think_llm"] = "claude-sonnet-4-5"
    config["quick_think_llm"] = "claude-haiku-4-5"
    config["max_debate_rounds"] = 1

    today = time.strftime("%Y-%m-%d")
    ta = TradingAgentsGraph(debug=False, config=config)

    print("  → Analyzing SPY...", flush=True)
    spy_state, spy_decision = ta.propagate("SPY", today)
    print("  → Analyzing QQQ...", flush=True)
    _, qqq_decision = ta.propagate("QQQ", today)

    # Ask Claude to reconcile both assessments
    prompt = f"""You are an expert market analyst. Compare these two independent market assessments made today.

== Assessment 1: Should I Trade? Dashboard ==
Composite Score: {your_score}/100
Decision: {your_decision}
Pillar Scores: {json.dumps(pillar_scores, indent=2)}

== Assessment 2: TradingAgents (LLM multi-agent) ==
SPY Decision: {str(spy_decision)[:800]}
QQQ Decision: {str(qqq_decision)[:800]}

Please provide:

## Agreement Points
Where do both assessments agree?

## Divergence Points
Where do they disagree, and what might explain the difference?

## Reconciliation
Given both assessments, what is your synthesized view for today's session?

## Meta-Observation
What does this comparison reveal about the strengths and blind spots of each approach?"""

    reconciliation = _ask_claude(prompt)

    ta_signal = str(spy_decision)[:100].split("\n")[0] if spy_decision else "N/A"
    table = (
        f"\n| Metric | Should I Trade? | TradingAgents (SPY) |\n"
        f"|--------|----------------|---------------------|\n"
        f"| Score/Decision | {your_score}/100 — **{your_decision}** | {ta_signal} |\n"
        f"| Source | 5-pillar rule-based | LLM multi-agent |\n"
        f"| Refresh | Every 60s | On-demand |\n"
    )

    header = f"# Signal Comparison\n_Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    return header + table + "\n---\n\n" + reconciliation


# ─── Mode 3: Code Review ────────────────────────────────────────────────────

def run_code_review() -> str:
    print("🔍 Running code review...", flush=True)

    files = {
        "scoring.py": _read_file("scoring.py")[:6000],
        "analysis.py": _read_file("analysis.py")[:3000],
        "data.py": _read_file("data.py")[:6000],
        "watchlist.py": _read_file("watchlist.py")[:4000],
    }

    combined = "\n\n".join(f"=== {name} ===\n{src}" for name, src in files.items())

    prompt = f"""You are a senior software engineer and quant reviewing a trading dashboard codebase.

{combined}

Review these Python files and provide structured findings grouped by severity:

## 🔴 Critical
Logic errors, incorrect calculations, data quality bugs, or security issues that could
cause wrong trading signals or crashes.

## 🟡 Warning
Subtle issues, edge cases in market data handling, potential staleness bugs, or patterns
that cause intermittent problems.

## 🔵 Suggestion
Maintainability improvements, scoring methodology refinements, or architectural suggestions.

For each finding:
- **File and approximate line**: e.g. `scoring.py ~line 42`
- **Issue**: What's wrong
- **Impact**: What could go wrong in production
- **Fix**: Specific corrective action

End with a **Summary**: overall code quality rating (1–10) and the single highest-priority fix."""

    result = _ask_claude(prompt)
    header = f"# Code Review\n_Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    return header + result


# ─── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Should I Trade? — Project Review CLI"
    )
    parser.add_argument("--methodology", action="store_true",
                        help="Critique 5-pillar scoring design (~30s)")
    parser.add_argument("--compare", action="store_true",
                        help="Compare TradingAgents vs your score (~3 min, server must run)")
    parser.add_argument("--code", action="store_true",
                        help="Code/logic review of source files (~60s)")
    parser.add_argument("--all", action="store_true", dest="all_modes",
                        help="Run all three modes and save report")
    args = parser.parse_args()

    if not any([args.methodology, args.compare, args.code, args.all_modes]):
        parser.print_help()
        sys.exit(1)

    sections: list[str] = []

    if args.methodology or args.all_modes:
        section = run_methodology_review()
        sections.append(section)
        print(section)

    if args.compare or args.all_modes:
        section = run_compare()
        sections.append(section)
        print(section)

    if args.code or args.all_modes:
        section = run_code_review()
        sections.append(section)
        print(section)

    if args.all_modes and sections:
        out_dir = _SCRIPT_DIR / "docs" / "reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y-%m-%d-%H-%M")
        out_path = out_dir / f"{ts}-review.md"
        out_path.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
        print(f"\n✅ Full review saved to {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('review.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 3: Smoke-test --methodology (requires ANTHROPIC_API_KEY)**

```bash
export $(grep -v '^#' .env | xargs)
python3 review.py --methodology
```

Expected: A structured Markdown critique printed to stdout in ~30 seconds. If you see an API error, check that `ANTHROPIC_API_KEY` in `.env` is correct.

- [ ] **Step 4: Commit**

```bash
git add review.py docs/
git commit -m "feat: add review.py CLI with --methodology, --compare, --code, --all modes"
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run all contract tests**

```bash
python3 -m pytest test_analysis_new.py -v
```

Expected: `6 passed`

- [ ] **Step 2: Run existing test suites**

```bash
python3 test_fixes.py && python3 test_scoring.py
```

Expected: same pass counts as before this feature branch (48 + 75).

- [ ] **Step 3: Smoke-test the full server**

```bash
export $(grep -v '^#' .env | xargs)
python3 server.py &
sleep 10
curl -s http://localhost:8765/api/dashboard | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('Score:', d['score'], '| Decision:', d['decision'])"
curl -s http://localhost:8765/api/analysis | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('Personas:', len(d['personas']), '| Source:', d.get('source','legacy'))"
kill %1
```

Expected:
```
Score: <number> | Decision: <YES/NO/CAUTION/...>
Personas: 5 | Source: legacy   ← legacy on first call; TradingAgents runs in background
```

- [ ] **Step 4: Final commit and push branch**

```bash
git add test_analysis_new.py
git commit -m "test: final verification — all tests pass after TradingAgents integration"
git push -u origin feat/tradingagents-integration
```

Then open a PR at https://github.com/Nabulizi/should-i-trade comparing `feat/tradingagents-integration` → `main`.
