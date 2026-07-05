"""notify.py — morning push report for the Daily Push feature.

Builds a one-message Markdown conditions report (score + day-over-day
deltas, posture, pillar breakdown, data quality, near-term event risk)
and sends it to any configured channel: Telegram bot API and/or Discord
webhook. Stdlib only — no pip dependencies, plain urllib POSTs.

Channels are configured in git-ignored config_local.py (or env vars,
which take priority): TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, and/or
DISCORD_WEBHOOK_URL. With neither configured, pushing is a silent no-op.

Run standalone to compute a fresh dashboard and push once:
    python3 notify.py
"""
from __future__ import annotations
import json, logging, os, urllib.request

import config

logger = logging.getLogger(__name__)

_PILLAR_ORDER = ("trend", "breadth", "momentum", "volatility", "macro")
_EVENT_WINDOW_DAYS = 3


def _fmt_delta(cur: int, prev: int | None) -> str:
    """'▲ +4' / '▼ -5' / '—' / '' (no baseline)."""
    if prev is None:
        return ""
    d = cur - prev
    if d > 0:
        return f"▲ +{d}"
    if d < 0:
        return f"▼ {d}"
    return "—"


def band_changed(data: dict, yesterday: dict | None) -> bool:
    """True when today's posture band differs from the previous close's."""
    return bool(yesterday) and data.get("decision") != yesterday.get("decision")


def build_report(data: dict, yesterday: dict | None) -> str:
    """Pure Markdown report: score+delta, posture, pillars, quality, events."""
    prev_total = yesterday["total"] if yesterday else None
    date = (data.get("market_state") or {}).get("et_date", "")
    lines = [f"*Should I Trade? — {date}*"]

    delta = _fmt_delta(data["total_score"], prev_total)
    delta_part = f" ({delta} vs prev close)" if delta else ""
    lines.append(f"*Score {data['total_score']}*{delta_part} — {data.get('decision', '')}")

    if band_changed(data, yesterday):
        lines.append(f"Posture change: {yesterday['decision']} → {data['decision']}")

    pillar_bits = []
    for p in _PILLAR_ORDER:
        score = data["pillars"][p]["score"]
        prev = yesterday["pillars"].get(p) if yesterday else None
        d = _fmt_delta(score, prev)
        pillar_bits.append(f"{p.capitalize()} {score}" + (f" ({d})" if d else ""))
    lines.append(" · ".join(pillar_bits))

    dq = data.get("data_quality", {})
    if not dq.get("valid", True):
        lines.append(f"⚠ Data degraded: {dq.get('message', 'live feeds unavailable')}")

    events = [f"{e['name']} {e['date_pretty']} ({e['days_until']}d)"
              for e in data.get("econ_events", [])
              if e.get("days_until", 99) <= _EVENT_WINDOW_DAYS]
    fomc = data.get("fomc") or {}
    if fomc.get("days_until") is not None and fomc["days_until"] <= _EVENT_WINDOW_DAYS:
        events.append(f"FOMC {fomc.get('date_pretty', '')} ({fomc['days_until']}d)")
    if events:
        lines.append("Events: " + " · ".join(events))

    lines.append(config.DASHBOARD_URL)
    return "\n".join(lines)
