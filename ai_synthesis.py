"""
ai_synthesis.py — Sub-agent trading desk roundtable via Gemini.

Five separate Gemini calls, each with a deep domain-expert system prompt.
Each agent reads the prior agents' actual outputs before speaking — true
sequential debate, not one model playing five roles simultaneously.

Chain: Technician -> Macro (sees Technician) -> Risk (sees both) ->
       Rotator (sees all three) -> Desk Head (adjudicates all four)

Falls back to the full rule-based roundtable on any failure.

API key: GEMINI_API_KEY env var or config.py
Free key (1 500 req/day): https://aistudio.google.com
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_NAME = "models/gemini-2.5-flash-lite"

# ─────────────────────────────────────────────────────────────────────────────
# Agent configurations — each is a fully independent expert persona
# ─────────────────────────────────────────────────────────────────────────────

_AGENTS = [
    {
        "key":    "technician",
        "persona": "The Technician",
        "role":   "Price Structure · MAs · RSI · MACD · Tape",
        "avatar": "📊",
        "system": (
            "You are The Technician at a professional prop trading firm. 20 years reading charts.\n"
            "Your only language is price, volume, and momentum — yields, Fed, narratives do not exist to you.\n\n"
            "Personality: Direct. Unapologetic. You speak FIRST in every roundtable — you set the frame.\n\n"
            "Your edge: tape character. Clean trend vs choppy grind vs extended blow-off. "
            "Fighting a clean trend or buying a choppy one is how amateurs blow up.\n\n"
            "Rules:\n"
            "- State OPINIONS not observations. 'Bull stack confirmed — offense pays' not 'SPY is above MAs.'\n"
            "- Name the exact entry signal: pullback to 20d? Failed breakdown? Breakout retest?\n"
            "- Name the one scenario where your call is wrong.\n"
            "- If structure is broken, say WAIT and say what must happen first.\n"
            "- Use the specific numbers from the data. Be sharp — traders act on this."
        ),
    },
    {
        "key":    "macro",
        "persona": "The Macro Strategist",
        "role":   "Yields · Dollar · Liquidity · Fed · BTC",
        "avatar": "🌐",
        "system": (
            "You are The Macro Strategist at a professional prop trading firm. "
            "You have run rates desks and watched chart setups get obliterated by macro regime shifts.\n\n"
            "Personality: Skeptical. Patient. You think in regimes, not trades. "
            "You have heard The Technician. Chart work is fine — until liquidity conditions change.\n\n"
            "Your edge: yield direction + dollar direction together tell you the liquidity regime. "
            "Falling yields + weak dollar = global bid on risk assets. "
            "Rising yields + strong dollar = the pain trade is coming regardless of chart structure.\n\n"
            "Rules:\n"
            "- REFERENCE The Technician by name. Tell them what macro confirms or overrides in their call.\n"
            "- State whether the REGIME is supportive or hostile to the technicals. Regime beats setup every time.\n"
            "- BTC is your liquidity canary — BTC cracking while SPY charts look fine means something is wrong.\n"
            "- Quantify FOMC proximity risk if relevant. It is the biggest near-term binary.\n"
            "- Use specific numbers. No vague macro commentary."
        ),
    },
    {
        "key":    "risk",
        "persona": "The Risk Manager",
        "role":   "VIX · SKEW · Flow · Breadth · Sizing",
        "avatar": "🛡",
        "system": (
            "You are The Risk Manager at a professional prop trading firm. "
            "Your job is not to say no — it is to say at what SIZE and with what STOPS the trade works.\n\n"
            "Personality: Precise. Unsentimental. You do not care about thesis — "
            "you care about whether you get paid for the risk you are taking.\n\n"
            "You have heard The Technician and The Macro Strategist debate. "
            "Now you tell them: does the risk-reward actually justify the bet at current vol levels?\n\n"
            "Your edge: VIX term structure. VIX9D vs VIX tells you near-term fear. "
            "SKEW tells you what smart money is hedging quietly. "
            "Calm VIX + elevated SKEW = someone knows something. "
            "RSP vs SPY breadth divergence tells you whether index strength is real.\n\n"
            "Rules:\n"
            "- REFERENCE at least one prior speaker by name. Challenge or build on their conclusion.\n"
            "- Lead with your vol read: is the risk-reward for what they are describing actually there?\n"
            "- Give a SPECIFIC position size recommendation: full / standard / half / minimal.\n"
            "- Name the ONE scenario where the bull case blows up — and how fast it happens."
        ),
    },
    {
        "key":    "rotator",
        "persona": "The Sector Rotator",
        "role":   "RS Rankings · Sector Flow · Leaders · IWM",
        "avatar": "🔄",
        "system": (
            "You are The Sector Rotator at a professional prop trading firm. "
            "While everyone else debates the index, you track where the actual MONEY is flowing. "
            "You do not trade themes — you trade relative strength.\n\n"
            "Personality: Pragmatic. Forward-looking. You do not care about narratives — you care about RS rankings.\n\n"
            "You have heard the full debate. Now you answer the only execution question: "
            "WHERE does the money go, and do sector flows confirm or contradict what the others said?\n\n"
            "Your edge: RS rankings show real money flows. "
            "IWM vs SPY is the most honest read of real risk appetite — not VIX, not headlines. "
            "When small caps lead, the risk-on is genuine. When only mega-caps hold the index, the rally is thin.\n\n"
            "Rules:\n"
            "- REFERENCE the prior debate. Which sectors confirm the bull case or expose flaws in it?\n"
            "- Name ONE sector to BUY now and ONE to AVOID — use the RS score. No conditionals.\n"
            "- IWM vs SPY divergence: what is it telling you that the index headline is not?\n"
            "- If leadership is defensive (utilities, staples), state clearly: the tape is lying."
        ),
    },
    {
        "key":    "desk_head",
        "persona": "The Desk Head",
        "role":   "Adjudicator · Final Call · Execution",
        "avatar": "🎯",
        "system": (
            "You are The Desk Head at a professional prop trading firm. "
            "25 years running trading desks. You have just heard your four best analysts debate.\n\n"
            "Personality: Decisive. Authoritative. You take sides. "
            "Balanced views lose money — you tell traders what to DO.\n\n"
            "Your job: adjudicate the debate, name who was right and why, "
            "name who missed something, give ONE clear directive with exact size and stop.\n\n"
            "Rules:\n"
            "- OPENING READ: first sentence names who won the argument and why. "
            "Second sentence names who you think missed something. Take a hard position.\n"
            "- FIRST POINT must be exactly: "
            "{\"icon\": \"🎯\", \"text\": \"VERDICT: <decision> · Score <score>/100 · <position_size>\"}\n"
            "- LAST POINT must be exactly: "
            "{\"icon\": \"⚡\", \"text\": \"EXECUTION: [one sentence: exact size, entry trigger, stop level]\"}\n"
            "- VERDICT line: the single most important thing a trader needs to hear. Max 15 words. Zero hedging.\n"
            "- You have exactly 4 points total (first=VERDICT, last=EXECUTION, two middle=sharp insights)."
        ),
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Lazy Gemini client
# ─────────────────────────────────────────────────────────────────────────────

_client = None
_client_loaded = False


def _get_client():
    global _client, _client_loaded
    if _client_loaded:
        return _client

    _client_loaded = True
    try:
        from google import genai  # type: ignore[import]
    except ImportError:
        logger.info("google-genai not installed. Run: pip3 install google-genai")
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        try:
            from config import GEMINI_API_KEY as cfg_key  # type: ignore[attr-defined]
            api_key = (cfg_key or "").strip()
        except (ImportError, AttributeError):
            pass

    if not api_key:
        logger.info("GEMINI_API_KEY not set — using rule-based roundtable.")
        return None

    try:
        _client = genai.Client(api_key=api_key)
        logger.info("Gemini sub-agent roundtable ready (%s).", _MODEL_NAME)
        return _client
    except Exception as exc:
        logger.warning("Gemini init failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Market data snapshot (shared across all agents)
# ─────────────────────────────────────────────────────────────────────────────

def _build_market_snapshot(dashboard: dict) -> str:
    pillars   = dashboard.get("pillars", {})
    macro_d   = pillars.get("macro",      {}).get("details", {})
    vol_d     = pillars.get("volatility", {}).get("details", {})
    trend_d   = pillars.get("trend",      {}).get("details", {})
    breadth_d = pillars.get("breadth",    {}).get("details", {})
    mom_d     = pillars.get("momentum",   {}).get("details", {})
    conflicts = dashboard.get("conflicts", [])
    warnings  = [c for c in conflicts if c.get("severity") == "warning"]

    sector_rs = mom_d.get("sector_rs", []) or []
    rs_top3 = [f"{s['name']} RS{s['rs_score']:+.1f}" for s in sector_rs[:3]  if s.get("rs_score") is not None]
    rs_bot3 = [f"{s['name']} RS{s['rs_score']:+.1f}" for s in sector_rs[-3:] if s.get("rs_score") is not None]

    snapshot = {
        "composite_score": dashboard.get("total_score"),
        "decision":        dashboard.get("decision"),
        "position_size":   dashboard.get("position_size"),
        "pillar_scores": {name: data.get("score") for name, data in pillars.items()},
        "trend": {
            "regime":       trend_d.get("regime"),
            "above_20d":    trend_d.get("above_20"),
            "above_50d":    trend_d.get("above_50"),
            "above_200d":   trend_d.get("above_200"),
            "tape_char":    trend_d.get("char_label"),
            "ath_dist_pct": trend_d.get("ath_dist"),
            "rsi14":        trend_d.get("rsi14"),
            "macd":         trend_d.get("macd_label"),
            "spy_chg_pct":  trend_d.get("spy_change_pct"),
        },
        "volatility": {
            "vix":          vol_d.get("vix_level"),
            "vix_label":    vol_d.get("vix_label"),
            "vix_trend":    vol_d.get("vix_trend"),
            "vix_pctile":   vol_d.get("vix_pctile"),
            "vix9d_label":  vol_d.get("vix9d_label"),
            "skew_label":   vol_d.get("skew_label"),
            "flow_label":   vol_d.get("flow_label"),
            "flow_score":   vol_d.get("flow_score"),
        },
        "macro": {
            "tnx_yield":       macro_d.get("tnx_value"),
            "yield_direction": macro_d.get("yield_direction"),
            "dxy_label":       macro_d.get("dxy_label"),
            "dxy_chg_pct":     macro_d.get("dxy_change_pct"),
            "btc_trend":       macro_d.get("btc_trend"),
            "btc_from_high":   macro_d.get("btc_from_high"),
            "fomc_days":       macro_d.get("fomc_days"),
        },
        "breadth": {
            "sectors_positive": breadth_d.get("sectors_positive"),
            "sectors_total":    breadth_d.get("sectors_total"),
            "rsp_vs_spy_pct":   breadth_d.get("rsp_vs_spy"),
            "iwm_vs_spy_pct":   mom_d.get("iwm_vs_spy"),
            "participation":    mom_d.get("participation"),
        },
        "rotation": {
            "rs_leaders":  rs_top3,
            "rs_laggards": rs_bot3,
        },
        "active_conflicts": [
            {"title": c["title"], "detail": c.get("detail", "")[:90]}
            for c in warnings
        ],
    }
    return json.dumps(snapshot, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Single agent call
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA_REMINDER = (
    "\n\nRespond with ONLY valid JSON (no markdown fences), this exact schema:\n"
    "{\n"
    '  "stance":       "<Bullish|Cautious|Defensive|Bearish>",\n'
    '  "stance_color": "<green|yellow|orange|red>",\n'
    '  "read":         "2-3 sharp sentences. Opinions not summaries. Reference prior speakers if any.",\n'
    '  "points":       [{"icon": "<emoji>", "text": "specific actionable insight"}],\n'
    '  "verdict":      "one decisive sentence, max 15 words"\n'
    "}\n"
    "Stance->color: Bullish=green, Cautious=yellow, Defensive=orange, Bearish=red.\n"
    "Non-Desk-Head: exactly 3 points. Desk Head: exactly 4 (first=VERDICT 🎯, last=EXECUTION ⚡)."
)

_PRIOR_HEADER = "\n\n─── PRIOR SPEAKERS (read these — challenge where you disagree) ───\n"


def _call_agent(
    client,
    agent: dict,
    market_snapshot: str,
    prior_speakers: list,
    cumulative_ms: int,
) -> Optional[dict]:
    """Call one sub-agent. Returns stamped persona dict or None."""
    try:
        from google.genai import types  # type: ignore[import]

        prior_text = ""
        if prior_speakers:
            lines = [
                f"{p['persona']} [{p['stance']}]: {p['read']}  -> Verdict: \"{p['verdict']}\""
                for p in prior_speakers
            ]
            prior_text = _PRIOR_HEADER + "\n".join(lines)

        user_prompt = (
            f"LIVE MARKET DATA:\n{market_snapshot}"
            f"{prior_text}"
            f"{_SCHEMA_REMINDER}"
        )

        t0 = time.time()
        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=agent["system"],
                temperature=0.75,
                max_output_tokens=700,
                response_mime_type="application/json",
            ),
        )
        elapsed_ms = round((time.time() - t0) * 1000)

        raw = (response.text or "").strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) >= 3 else parts[-1]
            raw = raw.lstrip("json").strip()

        parsed = json.loads(raw)
        required = ("stance", "stance_color", "read", "points", "verdict")
        if not all(k in parsed for k in required):
            logger.warning("%s response missing keys: %s", agent["persona"], list(parsed.keys()))
            return None

        logger.info("  %-24s [%s] in %dms", agent["persona"], parsed.get("stance", "?"), elapsed_ms)

        return {
            "persona":      agent["persona"],
            "role":         agent["role"],
            "avatar":       agent["avatar"],
            "stance":       parsed["stance"],
            "stance_color": parsed["stance_color"],
            "read":         parsed["read"],
            "points":       parsed["points"],
            "verdict":      parsed["verdict"],
            "ai_powered":   True,
            "latency_ms":   cumulative_ms + elapsed_ms,
        }

    except json.JSONDecodeError as exc:
        logger.warning("%s returned invalid JSON: %s", agent["persona"], exc)
        return None
    except Exception as exc:
        # On 429, check whether it's a short per-minute limit (retryable)
        # or daily quota exhaustion (not worth waiting for)
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            retry_s = _parse_retry_delay(msg)
            if retry_s is not None and retry_s <= 30:
                logger.info("%s hit RPM limit — retrying in %.0fs...", agent["persona"], retry_s)
                time.sleep(retry_s + 1)
                return _call_agent(client, agent, market_snapshot, prior_speakers, cumulative_ms)
            else:
                logger.warning("%s hit daily quota (retry=%s s) — fallback.", agent["persona"], retry_s)
                return None
        logger.warning("%s call failed (%s): %s", agent["persona"], type(exc).__name__, exc)
        return None


def _parse_retry_delay(error_msg: str) -> Optional[float]:
    """Extract retryDelay seconds from a Gemini 429 error message string."""
    import re
    m = re.search(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", error_msg)
    if m:
        return float(m.group(1))
    m = re.search(r"retry.*?(\d+(?:\.\d+)?)\s*s", error_msg, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def ai_roundtable(dashboard: dict) -> Optional[dict]:
    """
    Run the 5-agent sequential debate roundtable via Gemini.

    Each agent is a separate call with a deep domain-expert system prompt.
    Agents 2-5 receive all prior agents' outputs so they can challenge them.

    Returns {personas: [...], timestamp: ...} or None (triggers rule-based fallback).
    """
    client = _get_client()
    if client is None:
        return None

    t_start = time.time()
    logger.info("AI sub-agent roundtable starting (%d agents, %s)...", len(_AGENTS), _MODEL_NAME)

    market_snapshot = _build_market_snapshot(dashboard)
    speakers: list = []

    for agent in _AGENTS:
        cumulative_ms = round((time.time() - t_start) * 1000)
        result = _call_agent(client, agent, market_snapshot, speakers, cumulative_ms)
        if result is None:
            logger.warning("Agent %s failed — falling back to rule-based roundtable.", agent["persona"])
            return None
        speakers.append(result)

    total_s = time.time() - t_start
    logger.info("AI roundtable complete in %.1fs total.", total_s)

    return {
        "personas":  speakers,
        "timestamp": time.strftime("%H:%M UTC", time.gmtime()),
    }
