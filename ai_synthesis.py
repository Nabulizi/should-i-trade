"""
ai_synthesis.py — Gemini 2.0 Flash powered Desk Head synthesis.

Called by analysis.py as the AI-enhanced synthesis layer.
Returns None on any failure so the caller falls back to the rule-based
persona_desk_head() transparently — zero user-visible disruption.

Uses the current google-genai SDK (not the deprecated google-generativeai).

API key priority:
  1. GEMINI_API_KEY environment variable
  2. GEMINI_API_KEY in config.py

Get a free key (1 500 req/day) at https://aistudio.google.com
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_NAME = "gemini-2.0-flash"

# ── System prompt ──────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are the Desk Head at a professional prop trading firm. \
You receive four specialist analyses (Technician, Macro Strategist, Risk Manager, \
Sector Rotator) plus quantitative dashboard data, and you must produce the final synthesis \
that traders will act on.

Your voice: direct, opinionated, no hedging. Trading-floor language. \
Reference specific numbers from the input. Disagree with analysts when the data warrants it. \
Never invent data that is not present in the input.

Respond with ONLY valid JSON matching this exact schema — no markdown fences, no extra keys:
{
  "read": "string — 2-3 sentence opening synthesis. Weigh the analyst votes and highlight the most important conflict or alignment.",
  "points": [
    {"icon": "emoji", "text": "string — one specific, actionable observation"},
    {"icon": "emoji", "text": "..."},
    {"icon": "emoji", "text": "..."},
    {"icon": "emoji", "text": "..."}
  ],
  "verdict": "string — one crisp closing sentence, 15 words max"
}

Icon rules — use exactly these:
  ✅  bullish / positive confirmation
  ⚠️  caution / mixed signal
  🔴  bearish / hard risk
  🎯  key actionable call
  ⚡  execution / sizing rule

The FIRST point must always be:
  {"icon": "🎯", "text": "VERDICT: <decision> · Score <score>/100 · <position_size>"}

The LAST point must always be an ⚡ execution rule — one sentence on size and stops.
Total points: exactly 4.
"""

# ── Lazy client init ───────────────────────────────────────────────────────
_client = None
_client_loaded = False


def _get_client():
    """Lazily initialise Gemini client. Returns client or None."""
    global _client, _client_loaded
    if _client_loaded:
        return _client  # cached (may be None if unavailable)

    _client_loaded = True
    try:
        from google import genai  # type: ignore[import]
    except ImportError:
        logger.info(
            "google-genai not installed. "
            "Run: pip3 install google-genai   then set GEMINI_API_KEY."
        )
        return None

    # Resolve API key
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        try:
            from config import GEMINI_API_KEY as cfg_key  # type: ignore[attr-defined]
            api_key = (cfg_key or "").strip()
        except (ImportError, AttributeError):
            pass

    if not api_key:
        logger.info(
            "GEMINI_API_KEY not set — AI synthesis disabled. "
            "Set it in config.py or as an env var to enable."
        )
        return None

    try:
        _client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialised (%s) — AI synthesis active.", _MODEL_NAME)
        return _client
    except Exception as exc:
        logger.warning("Gemini init failed: %s", exc)
        return None


# ── Prompt builder ─────────────────────────────────────────────────────────

def _build_prompt(dashboard: dict, personas: list[dict]) -> str:
    """
    Produce a compact, information-rich prompt from live dashboard data
    and the four specialist persona outputs.
    """
    total     = dashboard.get("total_score", 0)
    decision  = dashboard.get("decision", "—")
    pos_size  = dashboard.get("position_size", "—")
    conflicts = dashboard.get("conflicts", [])
    warnings  = [c for c in conflicts if c.get("severity") == "warning"]

    pillars = dashboard.get("pillars", {})
    pillar_summary = " | ".join(
        f"{name.upper()} {data.get('score', '?')}/100"
        for name, data in pillars.items()
    )

    macro_d  = pillars.get("macro",       {}).get("details", {})
    vol_d    = pillars.get("volatility",  {}).get("details", {})
    trend_d  = pillars.get("trend",       {}).get("details", {})

    snapshot = {
        "score":            total,
        "decision":         decision,
        "position_size":    pos_size,
        "pillars":          pillar_summary,
        "vix":              vol_d.get("vix_level"),
        "vix_label":        vol_d.get("vix_label"),
        "flow_label":       vol_d.get("flow_label"),
        "tnx":              macro_d.get("tnx_value"),
        "yield_direction":  macro_d.get("yield_direction"),
        "dxy_label":        macro_d.get("dxy_label"),
        "btc_trend":        macro_d.get("btc_trend"),
        "fomc_days":        macro_d.get("fomc_days"),
        "regime":           trend_d.get("regime"),
        "above_200":        trend_d.get("above_200"),
        "char_label":       trend_d.get("char_label"),
        "active_conflicts": [
            {"title": c["title"], "detail": c.get("detail", "")[:90]}
            for c in warnings
        ],
    }

    persona_lines = "\n".join(
        f"- {p['persona']} [{p['stance']}]: {p['read'][:140].rstrip()} | Verdict: {p['verdict']}"
        for p in personas
    )

    return (
        f"MARKET DATA:\n{json.dumps(snapshot, indent=2)}\n\n"
        f"SPECIALIST ANALYSIS:\n{persona_lines}\n\n"
        "Write the Desk Head synthesis JSON now."
    )


# ── Public entry point ─────────────────────────────────────────────────────

def ai_desk_head(dashboard: dict, personas: list[dict]) -> Optional[dict]:
    """
    Generate an AI-powered Desk Head persona dict using Gemini.

    Returns a fully-formed persona dict (same shape as persona_desk_head)
    with two extra keys:  ai_powered=True, latency_ms=<int>.

    Returns None on any failure — caller falls back to rule-based silently.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        from google import genai  # type: ignore[import]
        from google.genai import types  # type: ignore[import]

        prompt = _build_prompt(dashboard, personas)
        t0 = time.time()

        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.45,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )
        elapsed = time.time() - t0

        raw = (response.text or "").strip()

        # Strip markdown fences if the model ignores response_mime_type
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) >= 3 else parts[-1]
            raw = raw.lstrip("json").strip()

        parsed = json.loads(raw)

        # Validate required keys
        if not all(k in parsed for k in ("read", "points", "verdict")):
            logger.warning("Gemini response missing required keys: %s", list(parsed.keys()))
            return None

        total = dashboard.get("total_score", 0)
        if total >= 75:
            stance, color = "Bullish",   "green"
        elif total >= 60:
            stance, color = "Cautious",  "yellow"
        elif total >= 45:
            stance, color = "Defensive", "orange"
        else:
            stance, color = "Bearish",   "red"

        logger.info("Gemini Desk Head synthesis completed in %.2fs", elapsed)

        return {
            "persona":      "The Desk Head",
            "role":         "AI Synthesis · Final call · Execution",
            "avatar":       "🎯",
            "stance":       stance,
            "stance_color": color,
            "read":         parsed["read"],
            "points":       parsed["points"],
            "verdict":      parsed["verdict"],
            "ai_powered":   True,
            "latency_ms":   round(elapsed * 1000),
        }

    except json.JSONDecodeError as exc:
        logger.warning("Gemini returned invalid JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Gemini synthesis failed (%s): %s", type(exc).__name__, exc)
        return None
