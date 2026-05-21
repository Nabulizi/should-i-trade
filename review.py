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
