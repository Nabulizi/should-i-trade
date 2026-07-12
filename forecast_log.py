"""
forecast_log.py — Prospective forecast log and self-grading (P3, decision D-009).

Every trading day at the EOD snapshot, one immutable forecast record is
appended to forecasts.jsonl. Outcomes are computed later from the next
session's OHLC against the formulas PREDECLARED in docs/prospective-log.md
and appended to forecast_outcomes.jsonl — forecasts are never mutated
(P3-011). This is live out-of-sample evidence: the score gets graded by
days it had not seen, not by retrospective tuning.

MVP scope: the 16:05 ET end-of-day track only (P3-001) — the concept the
2005-2026 replay actually tested. Intraday tracks (premarket/10:00/12:00)
are separate, unstarted tracks per the plan.

Storage (P3-010, Q-006): local JSONL next to this file. On the public Render
demo the filesystem is EPHEMERAL — records vanish on spin-down, so the demo
is explicitly flagged non-persistent in /health. Run locally (launchd/cron)
for a real archive.

CLI:
  python3 forecast_log.py            # status: counts, last date, gaps
  python3 forecast_log.py --grade    # grade pending forecasts (network)
  python3 forecast_log.py --audit    # integrity: duplicates, hashes, gaps
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FORECAST_FILE = os.path.join(SCRIPT_DIR, "forecasts.jsonl")
OUTCOME_FILE = os.path.join(SCRIPT_DIR, "forecast_outcomes.jsonl")

OBSERVATION_TRACK = "eod"

# Predeclared outcome parameters — change only with a new track/version and a
# docs/prospective-log.md update (P3-005..P3-008).
LARGE_MOVE_PCT = 1.5
"""|next-session close-to-close return| at or above this is a 'large move'."""

MIN_SAMPLE_FOR_DISPLAY = 60
"""No rolling metric is shown for a track below this many graded forecasts
(P3-009) — early numbers are noise theater."""


# ─── helpers ────────────────────────────────────────────────────────────────

def _engine_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=SCRIPT_DIR, capture_output=True, text=True,
                             timeout=5)
        sha = out.stdout.strip()
        return sha or None
    except Exception:
        return None


def _manifest_hash(record: dict) -> str:
    """Deterministic hash of everything except the hash field itself —
    lets --audit prove a record was not edited after the fact."""
    body = {k: v for k, v in record.items() if k != "input_manifest_hash"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _read_jsonl(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupt line in %s (%s) — loading valid prefix.", path, exc)
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    break
        return rows


def _append_jsonl(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


# ─── forecast recording (P3-001, P3-011) ───────────────────────────────────

def build_forecast_record(dashboard: dict, date_str: str) -> dict:
    """One immutable snapshot of what the model said, before outcomes exist."""
    as_of = dashboard.get("as_of") or {}
    record = {
        "forecast_date":      date_str,
        "observation_track":  OBSERVATION_TRACK,
        "model_version":      dashboard.get("model_version"),
        "engine_commit":      _engine_commit(),
        "calculated_at":      as_of.get("calculated_at"),
        "market_data_as_of":  as_of.get("market_data_as_of"),
        "market_session":     as_of.get("session"),
        "total_score":        dashboard.get("total_score"),
        "raw_total_score":    dashboard.get("raw_total_score"),
        "decision_band":      dashboard.get("natural_decision") or dashboard.get("decision"),
        "displayed_band":     dashboard.get("decision"),
        "pillars":            {k: v.get("score")
                               for k, v in (dashboard.get("pillars") or {}).items()},
        "reliability":        dashboard.get("reliability"),
        "volatility_budget":  dashboard.get("vol_target"),
        "data_sources":       dashboard.get("data_sources"),
    }
    record["input_manifest_hash"] = _manifest_hash(record)
    return record


def record_forecast(dashboard: dict, date_str: str) -> bool:
    """Append today's forecast. Idempotent: one record per
    (model_version, track, date); retries are safe (P3-011). Skips days with
    invalid data quality — a disabled reading is not a forecast.
    Returns True when a record was written."""
    if not (dashboard.get("data_quality") or {}).get("valid", False):
        logger.info("Forecast log: data quality invalid on %s — not recorded.", date_str)
        return False
    key = (dashboard.get("model_version"), OBSERVATION_TRACK, date_str)
    for row in _read_jsonl(FORECAST_FILE):
        if (row.get("model_version"), row.get("observation_track"),
                row.get("forecast_date")) == key:
            logger.info("Forecast log: %s already recorded — skipping.", date_str)
            return False
    _append_jsonl(FORECAST_FILE, build_forecast_record(dashboard, date_str))
    logger.info("Forecast log: recorded %s (track=%s).", date_str, OBSERVATION_TRACK)
    return True


# ─── outcome grading (P3-005..P3-008) ───────────────────────────────────────

def compute_outcome(forecast: dict, bars: list[dict]) -> dict | None:
    """Grade one forecast against the NEXT daily bar after forecast_date.

    Formulas are predeclared in docs/prospective-log.md:
      next_return_pct     = C1/C0 - 1                (close-to-close, %)
      range_size_pct      = (H1-L1)/C0               (%)
      range_efficiency    = |C1-O1|/(H1-L1)          (None when H1==L1)
      favorable_excursion = H1/C0 - 1                (%)
      adverse_excursion   = L1/C0 - 1                (%)
      large_move          = |next_return_pct| >= LARGE_MOVE_PCT

    Returns None when the reference or next bar is not available yet.
    """
    fdate = forecast["forecast_date"]
    idx = next((i for i, b in enumerate(bars) if b["date"] == fdate), None)
    if idx is None or idx + 1 >= len(bars):
        return None
    ref = bars[idx]
    nxt = bars[idx + 1]
    c0 = ref["close"]
    if not c0 or c0 <= 0:
        return None
    rng = nxt["high"] - nxt["low"]
    ret = (nxt["close"] / c0 - 1) * 100
    return {
        "forecast_date":     fdate,
        "observation_track": forecast["observation_track"],
        "model_version":     forecast["model_version"],
        "decision_band":     forecast["decision_band"],
        "total_score":       forecast["total_score"],
        "graded_at":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "next_bar_date":     nxt["date"],
        "next_return_pct":   round(ret, 3),
        "range_size_pct":    round(rng / c0 * 100, 3),
        "range_efficiency":  (round(abs(nxt["close"] - nxt["open"]) / rng, 3)
                              if rng > 0 else None),
        "favorable_excursion_pct": round((nxt["high"] / c0 - 1) * 100, 3),
        "adverse_excursion_pct":   round((nxt["low"] / c0 - 1) * 100, 3),
        "large_move":        abs(ret) >= LARGE_MOVE_PCT,
    }


def grade_pending(bars: list[dict] | None = None) -> int:
    """Grade every forecast that has no outcome yet and whose next bar
    exists. Appends to OUTCOME_FILE; never touches FORECAST_FILE. Returns
    the number of newly graded forecasts."""
    forecasts = _read_jsonl(FORECAST_FILE)
    if not forecasts:
        return 0
    if bars is None:
        from data import yf_ohlc_dated   # network import only when needed
        bars = yf_ohlc_dated("SPY", 400)
    if not bars:
        logger.warning("Forecast grading: no SPY bars available.")
        return 0
    done = {(o.get("model_version"), o.get("observation_track"), o.get("forecast_date"))
            for o in _read_jsonl(OUTCOME_FILE)}
    graded = 0
    for fc in forecasts:
        key = (fc.get("model_version"), fc.get("observation_track"),
               fc.get("forecast_date"))
        if key in done:
            continue
        outcome = compute_outcome(fc, bars)
        if outcome is not None:
            _append_jsonl(OUTCOME_FILE, outcome)
            graded += 1
    if graded:
        logger.info("Forecast grading: %d forecast(s) graded.", graded)
    return graded


# ─── audit & status (P3-012, P3-013) ────────────────────────────────────────

def audit() -> dict:
    """Integrity report: tampered records (hash mismatch), duplicate keys,
    and calendar gaps between consecutive forecasts (> 4 calendar days —
    long weekends are normal, longer runs mean missed observations)."""
    from datetime import date

    forecasts = _read_jsonl(FORECAST_FILE)
    tampered, dupes, gaps, seen = [], [], [], set()
    prev_date = None
    for row in sorted(forecasts, key=lambda r: r.get("forecast_date", "")):
        fdate = row.get("forecast_date", "?")
        if row.get("input_manifest_hash") != _manifest_hash(row):
            tampered.append(fdate)
        key = (row.get("model_version"), row.get("observation_track"), fdate)
        if key in seen:
            dupes.append(fdate)
        seen.add(key)
        if prev_date and fdate != "?":
            d0, d1 = date.fromisoformat(prev_date), date.fromisoformat(fdate)
            if (d1 - d0).days > 4:
                gaps.append(f"{prev_date} → {fdate}")
        prev_date = fdate if fdate != "?" else prev_date
    outcomes = _read_jsonl(OUTCOME_FILE)
    return {
        "forecasts": len(forecasts),
        "outcomes": len(outcomes),
        "ungraded": len(forecasts) - len(outcomes),
        "tampered": tampered,
        "duplicates": dupes,
        "gaps": gaps,
        "ok": not tampered and not dupes,
    }


def status() -> dict:
    """Lightweight health summary for /health (P3-013)."""
    forecasts = _read_jsonl(FORECAST_FILE)
    return {
        "track": OBSERVATION_TRACK,
        "count": len(forecasts),
        "last_forecast_date": forecasts[-1]["forecast_date"] if forecasts else None,
        "min_sample_for_display": MIN_SAMPLE_FOR_DISPLAY,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    if "--grade" in sys.argv:
        n = grade_pending()
        print(f"Graded {n} forecast(s).")
    elif "--audit" in sys.argv:
        report = audit()
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["ok"] else 1)
    else:
        print(json.dumps({**status(), **{k: v for k, v in audit().items()
                                         if k in ("outcomes", "ungraded", "gaps")}},
                         indent=2))
