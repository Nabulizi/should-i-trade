#!/usr/bin/env python3
"""
eod_job.py — standalone end-of-day snapshot + forecast + grading.

Runs the same work as the server's 16:05 ET scheduler job, without needing
the server to be up: records the daily close snapshot (daily_history.json),
appends the day's immutable forecast record (forecasts.jsonl, P3-001), and
grades any pending forecasts whose next session has completed.

Intended for launchd/cron on a machine where the server isn't running all
day. Safe by construction:
  - non-trading days (weekend/holiday) are a no-op
  - every write is idempotent (same-date replace / one record per day),
    so overlapping with a running server or a retry run is harmless
  - invalid data quality records nothing (a disabled reading is not a
    forecast)

Run:  python3 eod_job.py          # after the close on a trading day
Exit: 0 on success or clean no-op, 1 when live data was unusable.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("eod_job")


def run() -> int:
    from data import et_now, market_state
    from scoring import compute_dashboard
    from daily_history import record_daily_snapshot
    import forecast_log

    state = market_state()["state"]
    if state in ("weekend", "closed"):
        logger.info("Not a trading session (state=%s) — nothing to do.", state)
        return 0

    today = et_now().date().isoformat()
    data = compute_dashboard()
    if not data.get("data_quality", {}).get("valid", False):
        logger.warning("Live data invalid on %s — nothing recorded.", today)
        return 1

    snap = record_daily_snapshot(data, today)
    recorded = forecast_log.record_forecast(data, today)
    graded = forecast_log.grade_pending()
    logger.info("EOD job %s: snapshot=%s forecast=%s graded=%d score=%s (%s)",
                today, "ok" if snap else "skipped",
                "new" if recorded else "already-recorded", graded,
                data.get("total_score"), data.get("decision"))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    sys.exit(run())
