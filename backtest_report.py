"""
backtest_report.py - Build a product-grade Markdown report from replay output.

The expensive, networked replay lives in backtest.py. This module is deliberately
offline and deterministic: it reads the generated backtest_results.csv and turns
it into a concise evidence report that can be reviewed, tested, and committed.

Run:
    python3 backtest_report.py
    python3 backtest_report.py backtest_results.csv docs/backtest-report.md
"""

from __future__ import annotations

import csv
import hashlib
import math
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Literal, TypedDict

from backtest_stats import (
    BacktestRow,
    StrategyResult,
    _mean,
    _median,
    _std,
    band_mean_statistic,
    block_bootstrap_ci,
    calibrate_vol_exposures,
    count_flips,
    decile_spread_statistic,
    ic_statistic,
    max_drawdown,
    pearson,
    simulate_with_exposures,
    spearman,
    vol_target_strategy,
    yearly_table,
)

DEFAULT_INPUT = Path("backtest_results.csv")
DEFAULT_OUTPUT = Path("docs/backtest-report.md")
HORIZONS = (1, 5, 20)
COST_LEVELS_BPS = (0.0, 5.0, 10.0, 20.0)
ENGAGE_MIN = 55
FULL_RISK_MIN = 70
VALIDATION_START = "2016-01-01"
DECISION_ORDER = ("RISK-ON", "CONSTRUCTIVE", "SELECTIVE", "DE-RISK", "RISK-OFF")
PillarKey = Literal["v", "tr", "br", "mo", "ma", "total"]
PILLARS: tuple[tuple[PillarKey, str], ...] = (
    ("v", "Volatility"),
    ("tr", "Trend"),
    ("br", "Breadth"),
    ("mo", "Momentum"),
    ("ma", "Macro"),
    ("total", "TOTAL"),
)


def _engine_hash() -> str:
    """Return first 7 chars of HEAD commit hash, or 'unknown'.

    Deliberate tradeoff: this is provenance metadata only and never affects
    report math or test assertions. It has a hard 3-second timeout and
    degrades to 'unknown' outside a git checkout (CI, zip extracts, etc.).
    The subprocess call is intentional — injecting the hash via env var or
    build artifact was considered but adds more moving parts than it solves.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


class BandSummary(TypedDict):
    band: str
    n: int
    mean: float
    median: float
    hit_rate: float
    std: float
    mean_std: float


class DecileSummary(TypedDict):
    decile: int
    n: int
    score_min: float
    score_max: float
    mean: float
    hit_rate: float


class PillarIC(TypedDict):
    pillar: str
    ic5: float
    ic20: float


class RegimeSummary(TypedDict):
    regime: str
    n: int
    ic5: float
    mean5: float


def _to_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def load_rows(path: Path | str) -> list[BacktestRow]:
    rows: list[BacktestRow] = []
    with Path(path).open(newline="") as f:
        for raw in csv.DictReader(f):
            rows.append({
                "date": raw["date"],
                "total": float(raw["total"]),
                "raw_total": float(raw["raw_total"]),
                "decision": raw["decision"],
                "above_200": raw["above_200"].lower() == "true",
                "v": float(raw["v"]),
                "tr": float(raw["tr"]),
                "br": float(raw["br"]),
                "mo": float(raw["mo"]),
                "ma": float(raw["ma"]),
                "rsi2": _to_float(raw.get("rsi2", "")),
                "dist20": _to_float(raw.get("dist20", "")),
                "fwd1": float(raw["fwd1"]),
                "fwd5": float(raw["fwd5"]),
                "fwd20": float(raw["fwd20"]),
            })
    return rows


def information_coefficients(rows: list[BacktestRow]) -> dict[int, float]:
    scores = [r["total"] for r in rows]
    return {h: spearman(scores, [_forward_return(r, h) for r in rows]) for h in HORIZONS}


def _forward_return(row: BacktestRow, horizon: int) -> float:
    if horizon == 1:
        return row["fwd1"]
    if horizon == 5:
        return row["fwd5"]
    if horizon == 20:
        return row["fwd20"]
    raise ValueError(f"Unsupported horizon: {horizon}")


def _pillar_value(row: BacktestRow, key: PillarKey) -> float:
    if key == "v":
        return row["v"]
    if key == "tr":
        return row["tr"]
    if key == "br":
        return row["br"]
    if key == "mo":
        return row["mo"]
    if key == "ma":
        return row["ma"]
    return row["total"]


def _matched_exposure_strategy(rows: list[BacktestRow], timing_result: StrategyResult) -> StrategyResult:
    """Constant-fraction SPY baseline that matches the timing strategy's exposure.

    Instead of comparing 63%-invested timing against 100% buy-and-hold (unfair
    due to risk budget differences), this buys a fixed fraction every block so
    its total market exposure equals the timing strategy's. Same risk budget,
    no skill required.
    """
    exposure_frac = timing_result["exposure_pct"] / 100.0
    label = f"Constant {timing_result['exposure_pct']:.0f}% SPY (matched benchmark)"
    equity = 1.0
    curve = [equity]
    blocks: list[float] = []
    for i in range(0, len(rows), 5):
        row = rows[i]
        block_return = (row["fwd5"] / 100) * exposure_frac
        equity *= 1 + block_return
        blocks.append(block_return)
        curve.append(equity)
    years = len(rows) / 252.0
    total_blocks = len(blocks)
    invested_blocks = total_blocks  # always invested (at reduced fraction)
    cagr = (equity ** (1 / years) - 1) if years > 0 and equity > 0 else float("nan")
    sd = _std(blocks)
    sharpe = (_mean(blocks) / sd * math.sqrt(252 / 5)) if sd and sd > 0 else float("nan")
    return {
        "label": label,
        "total_return_pct": (equity - 1) * 100,
        "cagr_pct": cagr * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown(curve) * 100,
        "exposure_pct": timing_result["exposure_pct"],
        "invested_blocks": invested_blocks,
        "total_blocks": total_blocks,
    }


def band_rows(rows: list[BacktestRow]) -> list[BandSummary]:
    out: list[BandSummary] = []
    for band in DECISION_ORDER:
        vals = [r["fwd5"] for r in rows if r["decision"] == band]
        if not vals:
            continue
        mean = _mean(vals)
        std = _std(vals)
        out.append({
            "band": band,
            "n": len(vals),
            "mean": mean,
            "median": _median(vals),
            "hit_rate": 100 * sum(1 for x in vals if x > 0) / len(vals),
            "std": std,
            "mean_std": mean / std if std > 0 else float("nan"),
        })
    return out


def decile_rows(rows: list[BacktestRow]) -> list[DecileSummary]:
    ranked = sorted(rows, key=lambda r: r["total"])
    n = len(ranked)
    out: list[DecileSummary] = []
    for decile in range(10):
        lo = decile * n // 10
        hi = (decile + 1) * n // 10
        chunk = ranked[lo:hi]
        if not chunk:
            continue
        returns = [r["fwd5"] for r in chunk]
        scores = [r["total"] for r in chunk]
        out.append({
            "decile": decile + 1,
            "n": len(chunk),
            "score_min": min(scores),
            "score_max": max(scores),
            "mean": _mean(returns),
            "hit_rate": 100 * sum(1 for x in returns if x > 0) / len(returns),
        })
    return out


def pillar_ics(rows: list[BacktestRow]) -> list[PillarIC]:
    out: list[PillarIC] = []
    for key, label in PILLARS:
        out.append({
            "pillar": label,
            "ic5": spearman([_pillar_value(r, key) for r in rows], [r["fwd5"] for r in rows]),
            "ic20": spearman([_pillar_value(r, key) for r in rows], [r["fwd20"] for r in rows]),
        })
    return out


def regime_rows(rows: list[BacktestRow]) -> list[RegimeSummary]:
    regimes = (
        ("Bull tape (SPY > 200d)", [r for r in rows if r["above_200"]]),
        ("Bear tape (SPY < 200d)", [r for r in rows if not r["above_200"]]),
    )
    out: list[RegimeSummary] = []
    for label, subset in regimes:
        if not subset:
            continue
        out.append({
            "regime": label,
            "n": len(subset),
            "ic5": spearman([r["total"] for r in subset], [r["fwd5"] for r in subset]),
            "mean5": _mean(r["fwd5"] for r in subset),
        })
    return out


def strategy(rows: list[BacktestRow], label: str,
             condition: Callable[[BacktestRow], bool]) -> StrategyResult:
    equity = 1.0
    curve = [equity]
    blocks: list[float] = []
    invested_blocks = 0
    for i in range(0, len(rows), 5):
        row = rows[i]
        if condition(row):
            block_return = row["fwd5"] / 100
            equity *= 1 + block_return
            invested_blocks += 1
        else:
            block_return = 0.0
        blocks.append(block_return)
        curve.append(equity)

    years = len(rows) / 252.0
    total_blocks = len(blocks)
    cagr = (equity ** (1 / years) - 1) if years > 0 and equity > 0 else float("nan")
    sd = _std(blocks)
    sharpe = (_mean(blocks) / sd * math.sqrt(252 / 5)) if sd and sd > 0 else float("nan")
    return {
        "label": label,
        "total_return_pct": (equity - 1) * 100,
        "cagr_pct": cagr * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown(curve) * 100,
        "exposure_pct": 100 * invested_blocks / total_blocks if total_blocks else 0.0,
        "invested_blocks": invested_blocks,
        "total_blocks": total_blocks,
    }


def strategy_rows(rows: list[BacktestRow]) -> list[StrategyResult]:
    constructive = strategy(rows, f"Score >= {FULL_RISK_MIN} (CONSTRUCTIVE+)",
                            lambda r: r["total"] >= FULL_RISK_MIN)
    selective = strategy(rows, f"Score >= {ENGAGE_MIN} (SELECTIVE+)",
                         lambda r: r["total"] >= ENGAGE_MIN)
    buy_hold = strategy(rows, "Buy & hold", lambda r: True)
    return [
        constructive,
        _matched_exposure_strategy(rows, constructive),
        selective,
        _matched_exposure_strategy(rows, selective),
        vol_target_strategy(rows, selective["exposure_pct"]),
        buy_hold,
    ]


def _year_section(rows: list[BacktestRow], selective: StrategyResult) -> list[str]:
    matched_fraction = selective["exposure_pct"] / 100.0
    vol_exposures = calibrate_vol_exposures(rows, selective["exposure_pct"])
    years = yearly_table(rows, ENGAGE_MIN, matched_fraction, vol_exposures)
    beats = sum(1 for y in years if y["beat_benchmark"])
    lines = [
        "",
        "## Year-By-Year",
        "",
        f"Calendar-year returns. Matched-benchmark fraction and vol-target calibration are "
        f"full-sample ({selective['exposure_pct']:.0f}% exposure), so rows are comparable down "
        "each column. Block boundaries reset at year start (approximation).",
        "",
        f"The Score >= {ENGAGE_MIN} rule beat its matched benchmark in "
        f"**{beats} of {len(years)} years**.",
        "",
        f"| Year | Days | Mean Score | Score >= {ENGAGE_MIN} | Matched Const. | Vol-Target | Buy & Hold | Beat benchmark? |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for y in years:
        lines.append(
            f"| {y['year']} | {y['days']:,} | {y['mean_score']:.0f} | "
            f"{_fmt_pct(y['timing_return_pct'], 1)} | {_fmt_pct(y['matched_return_pct'], 1)} | "
            f"{_fmt_pct(y['vol_target_return_pct'], 1)} | {_fmt_pct(y['buy_hold_return_pct'], 1)} | "
            f"{'✓' if y['beat_benchmark'] else '✗'} |"
        )
    return lines


def _ci_row(label: str, point: float, lo: float, hi: float,
            fmt: Callable[[float], str]) -> str:
    if math.isnan(lo) or math.isnan(hi):
        return f"| {label} | {fmt(point)} | n/a | n/a |"
    excluded = "yes" if (lo > 0 or hi < 0) else "no"
    return f"| {label} | {fmt(point)} | [{fmt(lo)}, {fmt(hi)}] | {excluded} |"


def _significance_section(rows: list[BacktestRow]) -> list[str]:
    lines = [
        "",
        "## Statistical Significance",
        "",
        "Moving-block bootstrap (block 21 days, seeded, 95% CI). \"Zero excluded: no\" means",
        "the value is statistically indistinguishable from noise at this sample size.",
        "",
        "| Statistic | Point | 95% CI | Zero excluded |",
        "|---|---:|---:|:---:|",
    ]
    try:
        for horizon in HORIZONS:
            point, lo, hi = block_bootstrap_ci(rows, ic_statistic(horizon))
            lines.append(_ci_row(f"IC ({horizon}d)", point, lo, hi, _fmt_num))

        for band in DECISION_ORDER:
            if not any(r["decision"] == band for r in rows):
                continue
            point, lo, hi = block_bootstrap_ci(rows, band_mean_statistic(band))
            lines.append(_ci_row(f"Mean 5D, {band}", point, lo, hi, _fmt_pct))

        point, lo, hi = block_bootstrap_ci(rows, decile_spread_statistic)
        lines.append(_ci_row("Decile 1 - Decile 10 spread (5D)", point, lo, hi, _fmt_pct))
    except ValueError:
        lines.append("| (sample too small for block bootstrap) | n/a | n/a | n/a |")
    return lines


def _cost_section(rows: list[BacktestRow], selective: StrategyResult) -> list[str]:
    timing_exposures = [1.0 if r["total"] >= ENGAGE_MIN else 0.0 for r in rows]
    matched_fraction = selective["exposure_pct"] / 100.0
    constant_exposures = [matched_fraction] * len(rows)
    vol_exposures = calibrate_vol_exposures(rows, selective["exposure_pct"])
    flips = count_flips(timing_exposures)
    lines = [
        "",
        "## Transaction Cost Sensitivity",
        "",
        "Costs are charged on each change in exposure (including initial entry):",
        "cost = |delta exposure| x bps / 10,000. The constant benchmark pays once at",
        "inception; the vol-target baseline pays on its smaller continuous adjustments.",
        "",
        f"The Score >= {ENGAGE_MIN} rule made **{flips} exposure flips** over this sample.",
        "",
        "| Strategy | 0 bps | 5 bps | 10 bps | 20 bps |",
        "|---|---:|---:|---:|---:|",
    ]
    variants = (
        (f"Score >= {ENGAGE_MIN} (SELECTIVE+)", timing_exposures),
        (f"Constant {selective['exposure_pct']:.0f}% SPY", constant_exposures),
        (f"Vol-target {selective['exposure_pct']:.0f}%", vol_exposures),
    )
    for label, exposures in variants:
        cells = []
        for bps in COST_LEVELS_BPS:
            result = simulate_with_exposures(rows, exposures, label, cost_bps=bps)
            sharpe = "n/a" if math.isnan(result["sharpe"]) else f"{result['sharpe']:.2f}"
            cells.append(f"{_fmt_pct(result['total_return_pct'], 1)} (S {sharpe})")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def _fmt_pct(value: float, digits: int = 2) -> str:
    if math.isnan(value):
        return "n/a"
    return f"{value:+.{digits}f}%"


def _fmt_num(value: float, digits: int = 3) -> str:
    if math.isnan(value):
        return "n/a"
    return f"{value:+.{digits}f}"


def build_report(rows: list[BacktestRow], source_name: str = "backtest_results.csv") -> str:
    if len(rows) < 30:
        raise ValueError("Need at least 30 rows to build a meaningful report")

    ics = information_coefficients(rows)
    bands = band_rows(rows)
    deciles = decile_rows(rows)
    pillar_table = pillar_ics(rows)
    regimes = regime_rows(rows)
    full_sample_strategies = strategy_rows(rows)
    validation_rows = [r for r in rows if r["date"] >= VALIDATION_START]
    validation_strategies = strategy_rows(validation_rows) if len(validation_rows) >= 30 else []
    headline_strategies = validation_strategies or full_sample_strategies
    headline_rows = validation_rows if validation_strategies else rows
    # indices: 0=constructive, 1=matched-constructive, 2=selective,
    #          3=matched-selective, 4=vol-target, 5=buy&hold
    engage = headline_strategies[2]
    matched_engage = headline_strategies[3]
    vol_target = headline_strategies[4]
    buy_hold = headline_strategies[5]
    headline_label = (
        f"Validation window ({headline_rows[0]['date']} to {headline_rows[-1]['date']})"
        if validation_strategies else "Full sample"
    )
    generated_stamp = f"_Generated {date.today().isoformat()} · engine {_engine_hash()}_"
    timing_exposures = [1.0 if r["total"] >= ENGAGE_MIN else 0.0 for r in rows]
    flips = count_flips(timing_exposures)
    costed = simulate_with_exposures(
        rows, timing_exposures, "costed", cost_bps=10.0)

    lines = [
        "# Backtest Report",
        "",
        generated_stamp,
        "",
        "This report is generated from the per-day replay output produced by `backtest.py`.",
        "It supports the product claim that the Market Quality Score is a risk/exposure dial, not a day-by-day return predictor.",
        "",
        "## Executive Readout",
        "",
        f"- Full sample: {len(rows):,} trading days from {rows[0]['date']} to {rows[-1]['date']}.",
        f"- {headline_label}: Score >= {ENGAGE_MIN} produced {_fmt_pct(engage['total_return_pct'], 1)} total return with "
        f"{engage['sharpe']:.2f} Sharpe, {_fmt_pct(engage['max_drawdown_pct'], 1)} max drawdown, and "
        f"{engage['exposure_pct']:.0f}% market exposure.",
        f"- A constant {matched_engage['exposure_pct']:.0f}%-SPY baseline (same risk budget, no timing) returned "
        f"{_fmt_pct(matched_engage['total_return_pct'], 1)} with {matched_engage['sharpe']:.2f} Sharpe — the fair benchmark for the timing rule.",
        f"- A no-pillar vol-target baseline at the same exposure returned "
        f"{_fmt_pct(vol_target['total_return_pct'], 1)} with {vol_target['sharpe']:.2f} Sharpe and "
        f"{_fmt_pct(vol_target['max_drawdown_pct'], 1)} max drawdown — the score must beat this "
        f"to justify the five-pillar machinery.",
        f"- At 10 bps per exposure change ({flips} flips), the full-sample Score >= {ENGAGE_MIN} "
        f"total return drops to {_fmt_pct(costed['total_return_pct'], 1)}.",
        f"- Same-window buy & hold: {_fmt_pct(buy_hold['total_return_pct'], 1)} total return with "
        f"{buy_hold['sharpe']:.2f} Sharpe and {_fmt_pct(buy_hold['max_drawdown_pct'], 1)} max drawdown.",
        f"- Forward-return IC remains low ({_fmt_num(ics[5])} at 5 days), so the score should not be marketed as a precise return forecast.",
        "",
        "## Dataset",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Source CSV | `{source_name}` |",
        f"| Trading days | {len(rows):,} |",
        f"| First scored day | {rows[0]['date']} |",
        f"| Last scored day | {rows[-1]['date']} |",
        "",
        "## Information Coefficient",
        "",
        "Spearman correlation between the total score and forward SPY returns.",
        "",
        "| Horizon | IC |",
        "|---|---:|",
    ]
    for horizon in HORIZONS:
        lines.append(f"| {horizon} trading day | {_fmt_num(ics[horizon])} |")

    lines.extend([
        "",
        "## 5-Day Return By Decision Band",
        "",
        "Mean/Std (last column) is mean return divided by standard deviation — a volatility-adjusted signal quality score.",
        "Values above +0.15 indicate the band has a meaningful directional edge relative to its own noise.",
        "",
        "| Band | Days | Mean | Median | Hit Rate | Std Dev | Mean/Std |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for band in bands:
        mean_std_str = f"{band['mean_std']:+.3f}" if not math.isnan(band['mean_std']) else "n/a"
        lines.append(
            f"| {band['band']} | {band['n']:,} | {_fmt_pct(band['mean'])} | "
            f"{_fmt_pct(band['median'])} | {band['hit_rate']:.1f}% | {band['std']:.2f}% | {mean_std_str} |"
        )

    lines.extend([
        "",
        "## Score Deciles",
        "",
        "| Decile | Score Range | Days | Mean 5D Return | Hit Rate |",
        "|---:|---:|---:|---:|---:|",
    ])
    for decile in deciles:
        lines.append(
            f"| {decile['decile']} | {decile['score_min']:.0f}-{decile['score_max']:.0f} | "
            f"{decile['n']:,} | {_fmt_pct(decile['mean'])} | {decile['hit_rate']:.1f}% |"
        )

    lines.extend([
        "",
        "## Per-Pillar IC",
        "",
        "| Pillar | IC 5D | IC 20D |",
        "|---|---:|---:|",
    ])
    for pillar in pillar_table:
        lines.append(f"| {pillar['pillar']} | {_fmt_num(pillar['ic5'])} | {_fmt_num(pillar['ic20'])} |")

    lines.extend([
        "",
        "## Regime Split",
        "",
        "| Regime | Days | IC 5D | Mean 5D Return |",
        "|---|---:|---:|---:|",
    ])
    for regime in regimes:
        lines.append(
            f"| {regime['regime']} | {regime['n']:,} | {_fmt_num(regime['ic5'])} | {_fmt_pct(regime['mean5'])} |"
        )

    lines.extend([
        "",
        "## Strategy Comparison - Full Sample",
        "",
        "Non-overlapping 5-trading-day holds. Each timing strategy is paired with a constant-fraction SPY baseline",
        "that holds the same market exposure with no timing skill. Beat the matched baseline to demonstrate alpha.",
        "",
        "| Strategy | Total Return | CAGR | Sharpe | Max Drawdown | Exposure |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for strategy_result in full_sample_strategies:
        lines.append(
            f"| {strategy_result['label']} | {_fmt_pct(strategy_result['total_return_pct'], 1)} | "
            f"{_fmt_pct(strategy_result['cagr_pct'])} | {strategy_result['sharpe']:.2f} | "
            f"{_fmt_pct(strategy_result['max_drawdown_pct'], 1)} | {strategy_result['exposure_pct']:.0f}% |"
        )

    if validation_strategies:
        lines.extend([
            "",
            f"## Strategy Comparison - Validation Window ({validation_rows[0]['date']} to {validation_rows[-1]['date']})",
            "",
            "| Strategy | Total Return | CAGR | Sharpe | Max Drawdown | Exposure |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for strategy_result in validation_strategies:
            lines.append(
                f"| {strategy_result['label']} | {_fmt_pct(strategy_result['total_return_pct'], 1)} | "
                f"{_fmt_pct(strategy_result['cagr_pct'])} | {strategy_result['sharpe']:.2f} | "
                f"{_fmt_pct(strategy_result['max_drawdown_pct'], 1)} | {strategy_result['exposure_pct']:.0f}% |"
            )

    lines.extend(_year_section(rows, full_sample_strategies[2]))

    lines.extend(_significance_section(rows))

    lines.extend(_cost_section(rows, full_sample_strategies[2]))

    lines.extend([
        "",
        "## Product Interpretation",
        "",
        "- Keep the UI language centered on exposure quality and drawdown control.",
        "- Treat 55 as the validated engagement line; 70 is a stronger constructive regime, not the first usable signal.",
        "- Avoid claims that the score predicts individual profitable days.",
        "- Rerun the replay and regenerate this report whenever scoring formulas, weights, thresholds, or safety overrides change.",
        "",
        "## Limitations",
        "",
        "- Costs are modeled as linear bps on exposure changes only; no market impact, borrow, taxes, or execution delay.",
        "- SPY close-to-close returns only; no intraday fills, stops, or position management.",
        "- Calendar overlays are neutralized in the replay methodology.",
        "- Historical data vendor revisions can change results.",
        "- The score pillars are correlated, so the dashboard should not imply five fully independent votes.",
        "",
    ])
    return "\n".join(lines)


def write_report(input_path: Path | str = DEFAULT_INPUT,
                 output_path: Path | str = DEFAULT_OUTPUT) -> Path:
    input_file = Path(input_path)
    output_file = Path(output_path)
    rows = load_rows(input_file)
    report = build_report(rows, input_file.as_posix())
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report, encoding="utf-8")
    return output_file


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    input_path = Path(args[0]) if args else DEFAULT_INPUT
    output_path = Path(args[1]) if len(args) > 1 else DEFAULT_OUTPUT
    if not input_path.exists():
        print(f"Missing input CSV: {input_path}", file=sys.stderr)
        print("Run `python3 backtest.py` first to generate backtest_results.csv.", file=sys.stderr)
        return 2
    output_file = write_report(input_path, output_path)
    print(f"Backtest report written to {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
