# Next-Session Trading Conditions Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the pre-registered hypothesis that high-score days are followed by cleaner-trending sessions, and publish the verdict (PASS/FAIL) in the canonical backtest report.

**Architecture:** Three-stage extension of the existing pipeline. `backtest.py` (networked) additionally stores SPY's raw next-day OHLC in five new CSV columns; `backtest_stats.py` (pure) derives condition metrics and a decile-spread statistic; `backtest_report.py` renders a new section whose first result is the pre-registered verdict, computed with the existing seeded block bootstrap.

**Tech Stack:** Python 3.10+ stdlib only. Tests: `unittest` (`test_backtest_stats.py`, `test_backtest_report.py`).

**Spec:** `docs/superpowers/specs/2026-06-12-conditions-backtest-design.md`
**Branch:** `feat/conditions-backtest` (stacked on `feat/repositioning-copy-pass`; already checked out, spec committed).

**Key conventions:**
- `condition_metrics` returns `dict[str, float] | None` (NOT a TypedDict) — variable-key access into a TypedDict trips mypy's `literal-required` check, which CI enforces. `trend_day` is stored as `1.0`/`0.0`.
- Sign convention for the new spread statistic: **positive = high score better** (top decile minus bottom decile) — deliberately flipped vs the existing `decile_spread_statistic` (bottom minus top); both docstrings say so.
- New CSV columns are OPTIONAL everywhere: old CSVs must still produce a full report with a graceful-degrade message in the new section.

---

### Task 1: `backtest.py` — fetch opens, migrate cache, write five CSV columns

`backtest.py` has no test file (it is the networked stage); verification is `py_compile` plus a synthetic `align()` check. Do not run the full replay in this task.

**Files:**
- Modify: `backtest.py` (`_fetch` ~line 81, `load_all` ~line 117, `align` ~line 137, main loop ~lines 332–370)

- [ ] **Step 1: Keep Yahoo's `open` series in `_fetch`**

In the returned dict (currently `dates/adjclose/close/high/low/volume`), add one entry after `"close": closes,`:

```python
                "open": q.get("open", []),
```

Also update the docstring line to: `"""Return {dates:[iso], adjclose:[float|None], open/high/low/volume:[...]}."""`

- [ ] **Step 2: Cache migration in `load_all`**

Replace the cache-hit branch:

```python
        if not refresh and os.path.exists(cache):
            with open(cache) as f:
                out[sym] = json.load(f)
            continue
        print(f"  downloading {sym} …")
```

with:

```python
        if not refresh and os.path.exists(cache):
            with open(cache) as f:
                data = json.load(f)
            if "open" in data:
                out[sym] = data
                continue
            print(f"  {sym}: cached payload lacks 'open' — refetching …")
        else:
            print(f"  downloading {sym} …")
```

(The fall-through then hits the existing `data = _fetch(sym)` block unchanged.)

- [ ] **Step 3: Expose SPY raw open/close in `align`**

In `align()`, after `aligned["__SPY_VOL"] = col("volume")`, add:

```python
    aligned["__SPY_OPEN"] = col("open")
    aligned["__SPY_CLOSE_RAW"] = col("close")
```

And make `col` tolerant of payloads missing a key — change `for dt, v in zip(spy["dates"], spy[name]):` to `for dt, v in zip(spy["dates"], spy.get(name, [])):`

- [ ] **Step 4: Write the five columns in the main loop**

In `run()`, after `spy = aligned["SPY"]`, add:

```python
    spy_open = aligned["__SPY_OPEN"]
    spy_high = aligned["__SPY_HIGH"]
    spy_low = aligned["__SPY_LOW"]
    spy_close_raw = aligned["__SPY_CLOSE_RAW"]
```

Replace the `rows.append(...)` line:

```python
        rows.append({"date": master[i], **s, **{f"fwd{h}": fwd[h] for h in HORIZONS}})
```

with:

```python
        nd = {
            "nd_open": spy_open[i + 1], "nd_high": spy_high[i + 1],
            "nd_low": spy_low[i + 1], "nd_close": spy_close_raw[i + 1],
            "nd_prev_close": spy_close_raw[i],
        }
        rows.append({"date": master[i], **s,
                     **{f"fwd{h}": fwd[h] for h in HORIZONS},
                     **{k: (v if v is not None else "") for k, v in nd.items()}})
```

(`i + 1` is always in range: the loop ends at `n - max(HORIZONS)` and `max(HORIZONS)` is 20.)

In the CSV dump, extend the column list:

```python
        cols = (["date", "total", "raw_total", "decision", "above_200",
                 "v", "tr", "br", "mo", "ma", "rsi2", "dist20"]
                + [f"fwd{h}" for h in HORIZONS]
                + ["nd_open", "nd_high", "nd_low", "nd_close", "nd_prev_close"])
```

- [ ] **Step 5: Verify without network**

Run: `python3 -m py_compile backtest.py` (no output) and this synthetic check:

```bash
python3 -c "
import backtest
raw = {'SPY': {'dates': ['2024-01-02','2024-01-03'], 'adjclose': [100.0, 101.0],
               'close': [100.0, 101.0], 'open': [99.5, 100.5],
               'high': [101.0, 102.0], 'low': [99.0, 100.0], 'volume': [1, 1]}}
master, aligned = backtest.align(raw)
assert aligned['__SPY_OPEN'] == [99.5, 100.5], aligned['__SPY_OPEN']
assert aligned['__SPY_CLOSE_RAW'] == [100.0, 101.0]
raw['SPY'].pop('open')
master, aligned = backtest.align(raw)
assert aligned['__SPY_OPEN'] == [None, None]
print('align OK')
"
```

Expected: `align OK`

- [ ] **Step 6: Commit**

```bash
git add backtest.py
git commit -m "feat: replay stores SPY next-day raw OHLC for conditions analysis"
```

---

### Task 2: `backtest_stats.py` — condition metrics, spread statistic, tables

**Files:**
- Modify: `backtest_stats.py`
- Modify: `test_backtest_stats.py`

- [ ] **Step 1: Extend `make_rows` and write the failing tests**

In `test_backtest_stats.py`, extend `make_rows`'s signature with five keyword args, and the row dict with five entries:

```python
def make_rows(n, *, total=60.0, decision="SELECTIVE", fwd1=0.1, fwd5=0.5,
              fwd20=1.0, start="2020-01-01", nd_open=None, nd_high=None,
              nd_low=None, nd_close=None, nd_prev_close=None):
```

and inside the appended dict, after `"fwd20": float(at(fwd20, i)),`:

```python
            "nd_open": at(nd_open, i),
            "nd_high": at(nd_high, i),
            "nd_low": at(nd_low, i),
            "nd_close": at(nd_close, i),
            "nd_prev_close": at(nd_prev_close, i),
```

Then append this test class above the `__main__` footer:

```python
class TestConditionMetrics(unittest.TestCase):

    def _row(self, **kw):
        return make_rows(1, **kw)[0]

    def test_hand_computed_metrics(self):
        row = self._row(nd_open=100.0, nd_high=110.0, nd_low=98.0,
                        nd_close=109.0, nd_prev_close=100.0)
        m = backtest_stats.condition_metrics(row)
        self.assertAlmostEqual(m["range_eff"], 9.0 / 12.0, places=9)
        self.assertAlmostEqual(m["range_pct"], 12.0 / 100.0, places=9)
        self.assertAlmostEqual(m["gap_share"], 0.0, places=9)
        self.assertEqual(m["trend_day"], 1.0)

    def test_gap_share_caps_at_one(self):
        # Overnight gap (5) larger than the day's range (2).
        row = self._row(nd_open=105.0, nd_high=106.0, nd_low=104.0,
                        nd_close=104.5, nd_prev_close=100.0)
        m = backtest_stats.condition_metrics(row)
        self.assertAlmostEqual(m["gap_share"], 1.0, places=9)
        self.assertEqual(m["trend_day"], 0.0)  # |104.5-105|/2 = 0.25 < 0.6

    def test_missing_or_degenerate_inputs_return_none(self):
        self.assertIsNone(backtest_stats.condition_metrics(self._row()))
        self.assertIsNone(backtest_stats.condition_metrics(self._row(
            nd_open=100.0, nd_high=100.0, nd_low=100.0, nd_close=100.0,
            nd_prev_close=100.0)))  # H == L

    def test_spread_statistic_sign_convention(self):
        # Bottom-decile scores get choppy sessions (eff 0.1); top decile clean (0.9).
        # eff = |C-O|/(H-L) with H-L = 10: choppy C-O = 1, clean C-O = 9.
        closes = [101.0] * 10 + [105.0] * 80 + [109.0] * 10
        rows = make_rows(100, total=list(range(100)),
                         nd_open=100.0, nd_high=110.0, nd_low=100.0,
                         nd_close=closes, nd_prev_close=100.0)
        spread = backtest_stats.condition_decile_spread_statistic("range_eff")(rows)
        self.assertAlmostEqual(spread, 0.8, places=9)  # positive = high score better

    def test_spread_statistic_rejects_unknown_metric(self):
        with self.assertRaises(ValueError):
            backtest_stats.condition_decile_spread_statistic("sharpe")

    def test_spread_nan_when_no_valid_rows(self):
        rows = make_rows(100, total=list(range(100)))  # nd columns all None
        spread = backtest_stats.condition_decile_spread_statistic("range_eff")(rows)
        self.assertTrue(math.isnan(spread))

    def test_band_and_decile_tables(self):
        rows = (make_rows(30, decision="RISK-ON", total=90.0, nd_open=100.0,
                          nd_high=110.0, nd_low=100.0, nd_close=109.0,
                          nd_prev_close=100.0)
                + make_rows(30, decision="RISK-OFF", total=10.0, nd_open=100.0,
                            nd_high=110.0, nd_low=100.0, nd_close=101.0,
                            nd_prev_close=100.0, start="2020-03-01"))
        bands = backtest_stats.condition_band_table(rows, ("RISK-ON", "RISK-OFF"))
        self.assertEqual([b["label"] for b in bands], ["RISK-ON", "RISK-OFF"])
        self.assertEqual(bands[0]["n"], 30)
        self.assertAlmostEqual(bands[0]["range_eff"], 0.9, places=9)
        self.assertAlmostEqual(bands[0]["trend_day_pct"], 100.0, places=9)
        self.assertAlmostEqual(bands[1]["trend_day_pct"], 0.0, places=9)
        deciles = backtest_stats.condition_decile_table(rows)
        self.assertEqual(len(deciles), 10)
        self.assertAlmostEqual(deciles[0]["range_eff"], 0.1, places=9)
        self.assertAlmostEqual(deciles[-1]["range_eff"], 0.9, places=9)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 test_backtest_stats.py`
Expected: ERROR — `make_rows` accepts the new kwargs but `backtest_stats` has no attribute `condition_metrics`.

- [ ] **Step 3: Implement in `backtest_stats.py`**

a) Extend `BacktestRow` with five optional fields after `fwd20: float`:

```python
    nd_open: float | None
    nd_high: float | None
    nd_low: float | None
    nd_close: float | None
    nd_prev_close: float | None
```

b) Add near the other constants:

```python
TREND_DAY_MIN_EFF = 0.6
CONDITION_METRIC_KEYS = ("range_eff", "range_pct", "gap_share", "trend_day")
```

c) Append the functions:

```python
def condition_metrics(row: BacktestRow) -> dict[str, float] | None:
    """Next-session (T+1) trading-condition metrics from raw SPY OHLC.

    Returns a plain dict (not a TypedDict) keyed by CONDITION_METRIC_KEYS;
    trend_day is 1.0/0.0. Returns None when any input is missing or the
    session is degenerate (H <= L or prev close <= 0), so such rows drop
    out of every statistic.
    """
    o = row.get("nd_open")
    h = row.get("nd_high")
    low = row.get("nd_low")
    c = row.get("nd_close")
    prev = row.get("nd_prev_close")
    if o is None or h is None or low is None or c is None or prev is None:
        return None
    rng = h - low
    if rng <= 0 or prev <= 0:
        return None
    range_eff = abs(c - o) / rng
    return {
        "range_eff": range_eff,
        "range_pct": rng / prev,
        "gap_share": min(1.0, abs(o - prev) / rng),
        "trend_day": 1.0 if range_eff > TREND_DAY_MIN_EFF else 0.0,
    }


def condition_decile_spread_statistic(metric: str) -> Callable[[list[BacktestRow]], float]:
    """Top-decile minus bottom-decile mean of a next-session condition metric.

    Sign convention: POSITIVE means high-score days have the higher value —
    deliberately flipped versus decile_spread_statistic (bottom minus top),
    because here 'higher metric' (e.g. range efficiency) is the hypothesized
    benefit of a high score. Rows without valid metrics are excluded after
    ranking; NaN when either decile has no valid rows.
    """
    if metric not in CONDITION_METRIC_KEYS:
        raise ValueError(f"Unsupported condition metric: {metric}")

    def stat(rows: list[BacktestRow]) -> float:
        ranked = sorted(rows, key=lambda r: r["total"])
        tenth = len(ranked) // 10
        if tenth == 0:
            return float("nan")

        def decile_mean(chunk: list[BacktestRow]) -> float:
            vals = [m[metric] for r in chunk
                    if (m := condition_metrics(r)) is not None]
            return _mean(vals) if vals else float("nan")

        return decile_mean(ranked[-tenth:]) - decile_mean(ranked[:tenth])
    return stat


class ConditionSummary(TypedDict):
    label: str
    n: int
    range_eff: float
    range_pct: float
    gap_share: float
    trend_day_pct: float


def _condition_summary(label: str, chunk: list[BacktestRow]) -> ConditionSummary | None:
    metrics = [m for r in chunk if (m := condition_metrics(r)) is not None]
    if not metrics:
        return None
    return {
        "label": label,
        "n": len(metrics),
        "range_eff": _mean([m["range_eff"] for m in metrics]),
        "range_pct": _mean([m["range_pct"] for m in metrics]),
        "gap_share": _mean([m["gap_share"] for m in metrics]),
        "trend_day_pct": 100 * _mean([m["trend_day"] for m in metrics]),
    }


def condition_band_table(rows: list[BacktestRow],
                         band_order: tuple[str, ...]) -> list[ConditionSummary]:
    """Mean condition metrics per decision band (band_order is passed in so
    this module never imports backtest_report)."""
    out: list[ConditionSummary] = []
    for band in band_order:
        summary = _condition_summary(band, [r for r in rows if r["decision"] == band])
        if summary is not None:
            out.append(summary)
    return out


def condition_decile_table(rows: list[BacktestRow]) -> list[ConditionSummary]:
    """Mean condition metrics per score decile (1 = lowest scores)."""
    ranked = sorted(rows, key=lambda r: r["total"])
    n = len(ranked)
    out: list[ConditionSummary] = []
    for d in range(10):
        chunk = ranked[d * n // 10:(d + 1) * n // 10]
        summary = _condition_summary(str(d + 1), chunk)
        if summary is not None:
            out.append(summary)
    return out
```

- [ ] **Step 4: Run tests**

Run: `python3 test_backtest_stats.py && python3 test_backtest_report.py`
Expected: 33 OK and 13 OK. (The report suite must stay green: `load_rows` doesn't emit the new BacktestRow keys yet, but every consumer uses `.get` or named keys, and TypedDicts don't enforce completeness at runtime. If anything fails here, STOP — that's an unexpected coupling.)

- [ ] **Step 5: Commit**

```bash
git add backtest_stats.py test_backtest_stats.py
git commit -m "feat: next-session condition metrics, spread statistic, summary tables"
```

---

### Task 3: `backtest_report.py` — optional columns, conditions section, verdict

**Files:**
- Modify: `backtest_report.py`
- Modify: `test_backtest_report.py`

- [ ] **Step 1: Update the fixture and write failing tests**

In `test_backtest_report.py`, update `FIXTURE_CSV`: append `,nd_open,nd_high,nd_low,nd_close,nd_prev_close` to the header line, and append `,100.2,101.5,99.5,101.0,100.0` to EVERY data row (uniform values are fine: range_eff = 0.8/2.0 = 0.4, gap_share = 0.1, range_pct = 0.02, trend_day 0).

Then add these tests inside `TestBacktestReport`:

```python
    def test_report_contains_conditions_section_with_verdict(self):
        lines = FIXTURE_CSV.strip().split("\n")
        header, data = lines[0], lines[1:]
        shifted = [row.replace("2024-", "2025-", 1) for row in data]
        big_csv = "\n".join([header] + data + shifted) + "\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(big_csv, encoding="utf-8")
            rows = backtest_report.load_rows(path)
            report = backtest_report.build_report(rows, "fixture.csv")

        self.assertIn("## Next-Session Trading Conditions", report)
        self.assertIn("**VERDICT:", report)
        self.assertIn("Range efficiency (PRIMARY)", report)
        self.assertIn("(descriptive)", report)
        # Section order: after cost sensitivity, before product interpretation.
        self.assertLess(report.index("## Transaction Cost / Slippage Sensitivity"),
                        report.index("## Next-Session Trading Conditions"))
        self.assertLess(report.index("## Next-Session Trading Conditions"),
                        report.index("## Product Interpretation"))

    def test_conditions_section_degrades_without_nd_columns(self):
        # Rebuild the fixture WITHOUT the five nd columns (original schema).
        lines = FIXTURE_CSV.strip().split("\n")
        stripped = [",".join(row.split(",")[:15]) for row in lines]
        old_csv = "\n".join(stripped) + "\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.csv"
            path.write_text(old_csv, encoding="utf-8")
            rows = backtest_report.load_rows(path)
            report = backtest_report.build_report(rows, "fixture.csv")

        self.assertIn("## Next-Session Trading Conditions", report)
        self.assertIn("re-run `python3 backtest.py`", report)
        self.assertNotIn("**VERDICT:", report)
```

(15 = the original column count: date..dist20 is 12, plus fwd1/fwd5/fwd20.)

- [ ] **Step 2: Run to verify failure**

Run: `python3 test_backtest_report.py`
Expected: the two new tests FAIL (`'## Next-Session Trading Conditions' not found`); all 13 existing tests still pass (load_rows ignores unknown CSV columns — `csv.DictReader` exposes them but `load_rows` doesn't read them yet).

- [ ] **Step 3: Parse the optional columns in `load_rows`**

In `backtest_report.py`'s `load_rows`, after `"fwd20": float(raw["fwd20"]),` add:

```python
                "nd_open": _to_float(raw.get("nd_open", "") or ""),
                "nd_high": _to_float(raw.get("nd_high", "") or ""),
                "nd_low": _to_float(raw.get("nd_low", "") or ""),
                "nd_close": _to_float(raw.get("nd_close", "") or ""),
                "nd_prev_close": _to_float(raw.get("nd_prev_close", "") or ""),
```

(`or ""` guards `None` values that `DictReader` yields for short rows.)

- [ ] **Step 4: Implement the section**

a) Add to the `from backtest_stats import (...)` block (alphabetical):
`condition_band_table`, `condition_decile_spread_statistic`, `condition_decile_table`, `condition_metrics`.

b) Add a constant near `COST_LEVELS_BPS`:

```python
CONDITION_PRIMARY_METRIC = "range_eff"
```

c) Add after `_cost_section`:

```python
def _conditions_verdict(rows: list[BacktestRow]) -> tuple[str, float, float, float] | None:
    """(verdict, point, lo, hi) for the pre-registered H1, or None when the
    sample cannot support the bootstrap (no valid rows / too few rows)."""
    if not any(condition_metrics(r) is not None for r in rows):
        return None
    try:
        point, lo, hi = block_bootstrap_ci(
            rows, condition_decile_spread_statistic(CONDITION_PRIMARY_METRIC))
    except ValueError:
        return None
    if math.isnan(lo) or math.isnan(hi):
        return None
    return ("PASS" if lo > 0 else "FAIL", point, lo, hi)


def _conditions_section(rows: list[BacktestRow]) -> list[str]:
    lines = [
        "",
        "## Next-Session Trading Conditions",
        "",
        "Does a high score predict a better session to TRADE (not a higher return)?",
        "Metrics describe SPY's next session from raw daily OHLC: range efficiency",
        "|C-O|/(H-L) (1.0 = clean trend day, ~0 = round-trip chop), range size (H-L)/prevC,",
        "gap share (fraction of the move that happened overnight, untradeable), and",
        "trend-day frequency (efficiency > 0.6).",
        "",
    ]
    valid = [r for r in rows if condition_metrics(r) is not None]
    if not valid:
        lines.append("_No next-session OHLC columns in this CSV — re-run `python3 backtest.py` to populate them._")
        return lines

    verdict = _conditions_verdict(rows)
    lines.extend([
        "**Pre-registered H1:** next-session range efficiency is higher after",
        "top-decile score days than after bottom-decile days (95% block-bootstrap",
        "CI of the decile spread excludes zero, positive direction).",
        "",
    ])
    if verdict is None:
        lines.extend(["**VERDICT: insufficient sample**", ""])
    else:
        v, point, lo, hi = verdict
        lines.extend([
            f"Spread {point:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}].",
            "",
            f"**VERDICT: {v}**",
            "",
        ])

    lines.extend([
        "| Band | Valid Days | Range Eff | Range Size | Gap Share | Trend Days |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for b in condition_band_table(rows, DECISION_ORDER):
        lines.append(
            f"| {b['label']} | {b['n']:,} | {b['range_eff']:.3f} | "
            f"{100 * b['range_pct']:.2f}% | {b['gap_share']:.3f} | {b['trend_day_pct']:.1f}% |")

    lines.extend([
        "",
        "| Decile | Valid Days | Range Eff | Range Size | Gap Share | Trend Days |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for b in condition_decile_table(rows):
        lines.append(
            f"| {b['label']} | {b['n']:,} | {b['range_eff']:.3f} | "
            f"{100 * b['range_pct']:.2f}% | {b['gap_share']:.3f} | {b['trend_day_pct']:.1f}% |")

    lines.extend([
        "",
        "Decile 10 minus decile 1 spreads (positive = high score better):",
        "",
        "| Metric | Point | 95% CI | Zero excluded |",
        "|---|---:|---:|:---:|",
    ])
    metric_labels = (
        ("range_eff", "Range efficiency (PRIMARY)"),
        ("range_pct", "Range size (descriptive)"),
        ("gap_share", "Gap share (descriptive)"),
        ("trend_day", "Trend-day rate (descriptive)"),
    )

    def fmt3(x: float) -> str:
        return f"{x:+.3f}"

    try:
        for key, label in metric_labels:
            point, lo, hi = block_bootstrap_ci(rows, condition_decile_spread_statistic(key))
            lines.append(_ci_row(label, point, lo, hi, fmt3))
    except ValueError:
        lines.append("| (sample too small for block bootstrap) | n/a | n/a | n/a |")
    return lines
```

d) In `build_report`, immediately after `lines.extend(_cost_section(rows, full_sample_strategies[2]))`:

```python
    lines.extend(_conditions_section(rows))
```

e) Executive Readout: above the `lines = [` literal add:

```python
    cond_verdict = _conditions_verdict(rows)
```

and inside the readout list, after the 10 bps cost bullet, insert:

```python
        *([f"- Conditions hypothesis (cleaner next-session trends after high scores): "
           f"**{cond_verdict[0]}** — range-efficiency decile spread {cond_verdict[1]:+.3f}, "
           f"95% CI [{cond_verdict[2]:+.3f}, {cond_verdict[3]:+.3f}]."]
          if cond_verdict is not None else []),
```

f) Limitations: add two bullets before the correlated-pillars bullet:

```python
        "- Condition metrics proxy intraday quality from daily OHLC; no true intraday bars.",
        "- The gap metric uses raw prior close, so dividend days (~4/year) carry a small gap bias.",
```

- [ ] **Step 5: Run tests**

Run: `python3 test_backtest_report.py && python3 test_backtest_stats.py && python3 -m mypy models.py backtest_report.py backtest_stats.py --ignore-missing-imports --no-error-summary`
Expected: 15 OK, 33 OK, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add backtest_report.py test_backtest_report.py
git commit -m "feat: next-session trading-conditions section with pre-registered verdict"
```

---

### Task 4: Re-run the replay and publish the verdict

This task is networked and slow (~5–15 min total). The replay refetches every cached symbol (all lack `"open"`), then replays 5,373 days.

**Files:**
- Regenerate: `backtest_results.csv` (git-ignored), `docs/backtest-report.md`
- Modify: `docs/backtest-methodology.md`

- [ ] **Step 1: Snapshot the current report for the invariance check**

Run: `cp docs/backtest-report.md /tmp/report_before.md`

- [ ] **Step 2: Run the replay**

Run: `python3 backtest.py` (allow up to 15 minutes; the per-symbol refetch prints progress)
Expected: ends with `Per-day detail written to backtest_results.csv`. Then check the new columns: `head -1 backtest_results.csv` must end with `,nd_open,nd_high,nd_low,nd_close,nd_prev_close`, and `python3 -c "import csv; rows=list(csv.DictReader(open('backtest_results.csv'))); v=[r for r in rows if r['nd_open']]; print(len(rows), len(v))"` should show ≥ 95% of rows with non-empty nd_open.

- [ ] **Step 3: Regenerate the report**

Run: `time python3 backtest_report.py`
Expected: `Backtest report written to docs/backtest-report.md` (~60–90s; four extra bootstrap runs).

- [ ] **Step 4: Invariance check — pre-existing numbers must not change**

Run: `diff /tmp/report_before.md docs/backtest-report.md | head -60`
Expected: differences ONLY in (a) the generation-stamp line, (b) the new readout conditions bullet, (c) the new `## Next-Session Trading Conditions` section, (d) the two new Limitations bullets. Any changed number in strategy/IC/band/decile/year/cost tables is a STOP-and-report problem (the replay's forward returns still come from adjusted closes; they must be bit-identical).

- [ ] **Step 5: Record the verdict in the methodology doc**

In `docs/backtest-methodology.md`, append one bullet to the "Current Headline Claim" list, filling in the actual verdict from the regenerated report:

If PASS:
```markdown
- The pre-registered next-session conditions test PASSED: top-decile score
  days were followed by measurably cleaner-trending sessions (see the
  Next-Session Trading Conditions section of the report).
```

If FAIL:
```markdown
- The pre-registered next-session conditions test FAILED: top-decile score
  days were not followed by measurably cleaner-trending sessions (see the
  Next-Session Trading Conditions section of the report).
```

(The claim-hygiene test does not ban either word; verify with `python3 test_scoring.py 2>&1 | tail -1` → ALL PASS.)

- [ ] **Step 6: Commit (the verdict ships whatever it says)**

```bash
git add docs/backtest-report.md docs/backtest-methodology.md
git commit -m "feat: publish next-session conditions verdict from full 2005-2026 replay"
```

---

### Task 5: Final verification

- [ ] **Step 1: Full battery**

Run: `python3 -m unittest discover 2>&1 | tail -2 && python3 test_scoring.py 2>&1 | tail -1 && python3 -m mypy models.py backtest_report.py backtest_stats.py --ignore-missing-imports --no-error-summary && echo "mypy clean"`
Expected: OK / ALL PASS / mypy clean.

- [ ] **Step 2: Scope check**

Run: `git diff feat/repositioning-copy-pass --stat`
Expected files only: `backtest.py`, `backtest_stats.py`, `backtest_report.py`, `test_backtest_stats.py`, `test_backtest_report.py`, `docs/backtest-report.md`, `docs/backtest-methodology.md`, plus the spec/plan under `docs/superpowers/`.

- [ ] **Step 3: Read the regenerated conditions section end-to-end**

Verify internal consistency: the readout bullet's verdict equals the section's; the CI table's PRIMARY row matches the verdict numbers; band/decile tables have plausible valid-day counts (~5,300).

- [ ] **Step 4: Use superpowers:finishing-a-development-branch**
