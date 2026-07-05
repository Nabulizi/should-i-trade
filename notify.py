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


# ─── senders ──────────────────────────────────────────────────────────────

_HTTP_TIMEOUT = 10


def _channel(name: str) -> str:
    """Config lookup with env-var priority (matches GEMINI_API_KEY pattern)."""
    return os.environ.get(name) or getattr(config, name, "") or ""


def _post_json(url: str, payload: dict, label: str) -> bool:
    """POST JSON with one retry. Failures are logged, never raised."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    return True
                logger.warning("%s push HTTP %s (attempt %d)",
                               label, resp.status, attempt)
        except OSError as exc:
            logger.warning("%s push failed (attempt %d): %s", label, attempt, exc)
    return False


def send_telegram(text: str) -> bool:
    token, chat_id = _channel("TELEGRAM_BOT_TOKEN"), _channel("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False
    return _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        "telegram")


def send_discord(text: str) -> bool:
    url = _channel("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    return _post_json(url, {"content": text}, "discord")


def channels_configured() -> bool:
    return bool((_channel("TELEGRAM_BOT_TOKEN") and _channel("TELEGRAM_CHAT_ID"))
                or _channel("DISCORD_WEBHOOK_URL"))


def push_report(text: str, *, band_change: bool = True) -> int:
    """Send to every configured channel; returns how many accepted."""
    if not channels_configured():
        return 0
    if config.PUSH_ONLY_ON_BAND_CHANGE and not band_change:
        logger.info("Push skipped: posture band unchanged (low-noise mode).")
        return 0
    sent = 0
    if _channel("TELEGRAM_BOT_TOKEN") and _channel("TELEGRAM_CHAT_ID"):
        sent += send_telegram(text)
    if _channel("DISCORD_WEBHOOK_URL"):
        sent += send_discord(text)
    return sent


def send_now() -> int:
    """Compute a fresh dashboard and push the report once. Returns channels sent."""
    from scoring import compute_dashboard
    from daily_history import yesterday_snapshot
    from data import et_now
    data = compute_dashboard()
    yday = yesterday_snapshot(et_now().date().isoformat())
    text = build_report(data, yday)
    print(text)
    if not channels_configured():
        print("\n(no channel configured — set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID "
              "or DISCORD_WEBHOOK_URL in config_local.py)")
        return 0
    return push_report(text, band_change=band_changed(data, yday))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"\nDelivered to {send_now()} channel(s).")
