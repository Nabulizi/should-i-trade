"""
ai_synthesis.py — Sub-agent roundtable via Gemini (five analytical lenses).

Five separate Gemini calls over ONE shared market snapshot. Each lens reads
the prior lenses' outputs before speaking, so later lenses can note agreement
or disagreement — but they are views of the same data, not independent
analysts, and their output is bounded to evidence: what the supplied fields
support, what contradicts it, what is missing, and what would falsify the
read (P1-021/P1-022, decision D-008). No entries, stops, targets, or sizing.

Chain: Technician -> Macro (sees Technician) -> Risk (sees both) ->
       Rotator (sees all three) -> Desk Head (synthesizes all four)

Falls back to the full rule-based roundtable on any failure, including
schema-validation failure of the model output (P1-023).

API key: GEMINI_API_KEY env var or git-ignored config_local.py
Free key (1 500 req/day): https://aistudio.google.com
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_NAME = "models/gemini-2.5-flash"

# ─────────────────────────────────────────────────────────────────────────────
# Lens configurations. Shared constraints (D-008, P1-021/P1-022): no invented
# credentials or employment, no authority theater, no trade instructions —
# every claim traces to a supplied field; every lens names contradicting and
# missing evidence and what would falsify its read.
# ─────────────────────────────────────────────────────────────────────────────

_LENS_GROUND_RULES = (
    "\n\nGround rules (mandatory):\n"
    "- You are an analytical lens of a market-conditions dashboard, not a person. "
    "Do not claim experience, employment, credentials, or a track record.\n"
    "- Every claim must trace to a field in the supplied data. If a field is "
    "missing or null, say so instead of guessing.\n"
    "- State what supports your read, what contradicts it, and what single "
    "observation would falsify it.\n"
    "- You and the other lenses read the SAME snapshot — agreement between "
    "lenses is not independent confirmation.\n"
    "- NEVER give trade instructions: no entries, exits, stops, targets, "
    "position sizes, or buy/sell/avoid directives. Describe conditions only.\n"
    "- Plain, specific sentences. Use the actual numbers."
)

_AGENTS = [
    {
        "key":    "technician",
        "persona": "The Technician",
        "role":   "Price Structure · MAs · RSI · MACD · Tape",
        "avatar": "📊",
        "system": (
            "You are the price-structure lens. You read only the supplied trend "
            "fields: SPY/QQQ vs the 20/50/200d MAs, RSI, MACD, tape character, "
            "distance from the 52-week high, and today's change.\n\n"
            "Your question: is price structure intact, repairing, extended, or "
            "broken — and does today's tape character (trending / choppy / "
            "extended) confirm or contradict that structure?\n"
            "You speak first; do not reference other lenses."
            + _LENS_GROUND_RULES
        ),
    },
    {
        "key":    "macro",
        "persona": "The Macro Strategist",
        "role":   "Yields · Dollar · Liquidity · Fed · BTC",
        "avatar": "🌐",
        "system": (
            "You are the macro-conditions lens. You read only the supplied macro "
            "fields: 10Y yield level and direction, dollar trend, BTC trend (a "
            "rough liquidity proxy), and FOMC proximity.\n\n"
            "Your question: is the macro backdrop supportive, neutral, or "
            "hostile to the price structure The Technician described? Note "
            "where macro agrees or disagrees with that lens — remembering both "
            "of you read the same snapshot. Quantify FOMC proximity if the "
            "data shows a meeting within ten days."
            + _LENS_GROUND_RULES
        ),
    },
    {
        "key":    "risk",
        "persona": "The Risk Manager",
        "role":   "VIX · VIX9D · SKEW · Flow · Breadth",
        "avatar": "🛡",
        "system": (
            "You are the volatility-and-stress lens. You read only the supplied "
            "vol fields: VIX level/trend/percentile, VIX9D and SKEW labels, "
            "flow sentiment, and RSP-vs-SPY breadth divergence.\n\n"
            "Your question: how fragile are current conditions? Is near-term "
            "or tail stress elevated, is the index masking weak breadth, and "
            "which single vol indicator would most change this read if it "
            "flipped? Note agreement or disagreement with the prior lenses."
            + _LENS_GROUND_RULES
        ),
    },
    {
        "key":    "rotator",
        "persona": "The Sector Rotator",
        "role":   "RS Rankings · Sector Flow · Leaders · IWM",
        "avatar": "🔄",
        "system": (
            "You are the participation lens. You read only the supplied "
            "rotation fields: sector RS leaders and laggards, IWM vs SPY, "
            "sectors positive, and the participation label.\n\n"
            "Your question: is participation broad or narrow, which sectors "
            "lead and lag by RS (describe — do not tell anyone to buy or "
            "avoid them), and does defensive vs cyclical leadership confirm "
            "or contradict the prior lenses' reads?"
            + _LENS_GROUND_RULES
        ),
    },
    {
        "key":    "desk_head",
        "persona": "The Desk Head",
        "role":   "Synthesis · Agreement & Conflicts",
        "avatar": "🎯",
        "system": (
            "You are the synthesis lens. You have read four other lenses of "
            "the SAME market snapshot — their agreement is overlap, not "
            "independent confirmation.\n\n"
            "Your job: state where the lenses agree, where they genuinely "
            "disagree, which evidence is missing or stale, and what would "
            "falsify the overall read.\n\n"
            "Structure rules:\n"
            "- FIRST POINT must be exactly: "
            "{\"icon\": \"🎯\", \"text\": \"VERDICT: <decision> · Score <score>/100 · <position_size>\"} "
            "using the supplied composite fields verbatim.\n"
            "- LAST POINT must be exactly: "
            "{\"icon\": \"⚡\", \"text\": \"CONDITIONS: [one sentence: the conditions tier and the single biggest open risk]\"}\n"
            "- You have exactly 4 points (first=VERDICT, last=CONDITIONS, two "
            "middle points on agreement/disagreement/missing evidence)."
            + _LENS_GROUND_RULES
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
    '  "read":         "2-3 plain sentences grounded in supplied fields. No trade instructions.",\n'
    '  "points":       [{"icon": "<emoji>", "text": "specific evidence-based observation"}],\n'
    '  "verdict":      "one plain summary sentence, max 15 words, no directives"\n'
    "}\n"
    "Stance->color: Bullish=green, Cautious=yellow, Defensive=orange, Bearish=red.\n"
    "Non-Desk-Head: exactly 3 points. Desk Head: exactly 4 (first=VERDICT 🎯, last=CONDITIONS ⚡)."
)

_PRIOR_HEADER = "\n\n─── PRIOR LENSES (same snapshot — note agreement and disagreement) ───\n"

# ── Output validation (P1-023) ───────────────────────────────────────────────
# The model's output is untrusted. Constrain stances, derive colors (never
# trust them), clamp text lengths and point counts; any structural problem
# returns None → rule-based fallback.
_ALLOWED_STANCES = {"Bullish": "green", "Cautious": "yellow",
                    "Defensive": "orange", "Bearish": "red"}
_MAX_READ_CHARS    = 600
_MAX_VERDICT_CHARS = 140
_MAX_POINT_CHARS   = 280
_MAX_POINTS        = 5


def _validate_persona(parsed: dict) -> Optional[dict]:
    """Sanitize one lens response; None when unusable (triggers fallback)."""
    if not isinstance(parsed, dict):
        return None
    try:
        stance = str(parsed["stance"]).strip().title()
        if stance not in _ALLOWED_STANCES:
            return None
        read = str(parsed["read"]).strip()
        verdict = str(parsed["verdict"]).strip()
        raw_points = parsed["points"]
    except (KeyError, TypeError):
        return None
    if not read or not verdict or not isinstance(raw_points, list) or not raw_points:
        return None
    points = []
    for pt in raw_points[:_MAX_POINTS]:
        if not isinstance(pt, dict):
            return None
        text = str(pt.get("text", "")).strip()
        if not text:
            return None
        points.append({"icon": str(pt.get("icon", "•"))[:4],
                       "text": text[:_MAX_POINT_CHARS]})
    return {
        "stance":       stance,
        "stance_color": _ALLOWED_STANCES[stance],
        "read":         read[:_MAX_READ_CHARS],
        "points":       points,
        "verdict":      verdict[:_MAX_VERDICT_CHARS],
    }


def _call_agent(
    client,
    agent: dict,
    market_snapshot: str,
    prior_speakers: list,
    cumulative_ms: int,
) -> Optional[dict]:
    """Call one sub-agent. Returns stamped persona dict or None."""
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

    for attempt in range(3):
        raw = ""
        try:
            t0 = time.time()
            response = client.models.generate_content(
                model=_MODEL_NAME,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=agent["system"],
                    temperature=0.75,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            elapsed_ms = round((time.time() - t0) * 1000)

            raw = (response.text or "").strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) >= 3 else parts[-1]
                raw = raw.lstrip("json").strip()

            parsed = json.loads(raw)
            clean = _validate_persona(parsed)
            if clean is None:
                logger.warning("%s response failed schema validation — fallback.",
                               agent["persona"])
                return None

            logger.info("  %-24s [%s] in %dms", agent["persona"], clean["stance"], elapsed_ms)

            return {
                "persona":      agent["persona"],
                "role":         agent["role"],
                "avatar":       agent["avatar"],
                **clean,
                "ai_powered":   True,
                "latency_ms":   cumulative_ms + elapsed_ms,
            }

        except json.JSONDecodeError as exc:
            logger.warning("%s returned invalid JSON: %s\nRaw: %r", agent["persona"], exc, raw)
            return None
        except Exception as exc:
            # On 429, check whether it's a short per-minute limit (retryable)
            # or daily quota exhaustion (not worth waiting for)
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                retry_s = _parse_retry_delay(msg)
                if retry_s is not None and retry_s <= 30 and attempt < 2:
                    logger.info("%s hit RPM limit — retrying in %.0fs (attempt %d/3)...", agent["persona"], retry_s, attempt + 1)
                    time.sleep(retry_s + 1)
                    continue
                else:
                    logger.warning("%s hit daily quota or retry limit (retry=%s s) — fallback.", agent["persona"], retry_s)
                    return None
            logger.warning("%s call failed (%s): %s", agent["persona"], type(exc).__name__, exc)
            return None

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
        # Provenance (P1-024): model, generation time, and the shared-input
        # limitation are part of the payload, not fine print.
        "engine":       "gemini",
        "model":        _MODEL_NAME,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": ("5 AI lenses over one shared data snapshot — "
                 "not independent analysts; agreement is overlap, not confirmation."),
    }
