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

import analysis_legacy

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

    Verified state keys (v0.2.x, confirmed via probe 2026-05-21):
      state.get("market_report")              — technical summary
      state.get("sentiment_report")           — sentiment analysis
      state.get("news_report")                — news analysis
      state.get("fundamentals_report")        — fundamentals analysis
      state.get("investment_debate_state", {})
        .get("bear_history")                  — list of bear debate turns
        .get("bull_history")                  — list of bull debate turns
        .get("judge_decision")                — judge's final call
      state.get("trader_investment_plan")     — trader's plan text
      state.get("final_trade_decision")       — final decision string (e.g. "Overweight")

    If a key is missing, the corresponding legacy persona's read is preserved.
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

    # 2 — Risk Manager ← last bear debate turn (bear_history is a list)
    bear_history = debate.get("bear_history") or []
    bear_raw = bear_history[-1] if bear_history else None
    bear_text = _text(bear_raw)
    if bear_text:
        personas[2]["read"] = bear_text

    # 3 — Rotator/Quant ← last bull debate turn (bull_history is a list)
    bull_history = debate.get("bull_history") or []
    bull_raw = bull_history[-1] if bull_history else None
    bull_text = _text(bull_raw)
    if bull_text:
        personas[3]["read"] = bull_text

    # 4 — Desk Head ← trader plan + final decision
    plan_text = _text(state.get("trader_investment_plan") or desk_summary)
    if plan_text:
        personas[4]["read"] = plan_text
    final_decision = _text(state.get("final_trade_decision") or spy_decision, 200)
    if final_decision:
        personas[4]["verdict"] = final_decision

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
        return analysis_legacy.roundtable(dashboard)

    legacy = analysis_legacy.roundtable(dashboard)
    _maybe_refresh(dashboard, legacy)
    return stale if stale is not None else legacy
