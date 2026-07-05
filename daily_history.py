"""daily_history.py — one end-of-day snapshot per trading day.

Feeds the "Since yesterday" dashboard strip and the morning push report.
Storage: daily_history.json (git-ignored, auto-created, atomic writes),
newest entry last, capped at config.DAILY_HISTORY_MAXLEN.
"""
from __future__ import annotations
import json, logging, os, tempfile

from config import DAILY_HISTORY_MAXLEN

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_HISTORY_FILE = os.path.join(SCRIPT_DIR, "daily_history.json")

_PILLARS = ("volatility", "trend", "breadth", "momentum", "macro")


def load_daily_history(path: str = DAILY_HISTORY_FILE) -> list[dict]:
    """Load snapshots from disk; corrupt or missing file yields []."""
    try:
        with open(path, encoding="utf-8") as f:
            hist = json.load(f)
        return hist if isinstance(hist, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("daily_history.json corrupt (%s) — starting fresh.", exc)
        return []


def _save(history: list[dict], path: str) -> None:
    dir_ = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".daily_tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(history, f)
        os.replace(tmp_path, path)
    except OSError:
        logger.exception("Failed to save daily_history.json")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def record_daily_snapshot(data: dict, et_date: str,
                          path: str = DAILY_HISTORY_FILE) -> dict | None:
    """Append (or same-date replace) a close snapshot built from a dashboard payload.

    Returns the snapshot, or None when data quality is invalid (no fake closes).
    """
    if not data.get("data_quality", {}).get("valid", True):
        logger.warning("EOD snapshot skipped for %s — data quality invalid.", et_date)
        return None
    snapshot = {
        "date": et_date,
        "total": data["total_score"],
        "decision": data.get("decision", ""),
        "pillars": {p: data["pillars"][p]["score"] for p in _PILLARS},
    }
    history = [s for s in load_daily_history(path) if s.get("date") != et_date]
    history.append(snapshot)
    history.sort(key=lambda s: s.get("date", ""))
    _save(history[-DAILY_HISTORY_MAXLEN:], path)
    return snapshot


def yesterday_snapshot(today_date: str,
                       path: str = DAILY_HISTORY_FILE) -> dict | None:
    """Newest snapshot strictly before today_date (ISO yyyy-mm-dd), else None."""
    prior = [s for s in load_daily_history(path) if s.get("date", "") < today_date]
    return prior[-1] if prior else None
