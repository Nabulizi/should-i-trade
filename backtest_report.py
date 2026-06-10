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
import math
import sys
from pathlib import Path
from typing import Callable, Iterable, Literal, TypedDict


DEFAULT_INPUT = Path("backtest_results.csv")
DEFAULT_OUTPUT = Path("docs/backtest-report.md")
HORIZONS = (1, 5, 20)
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


class BacktestRow(TypedDict):
    date: str
    total: float
    raw_total: float
    decision: str
    above_200: bool
    v: float
    tr: float
    br: float
    mo: float
    ma: float
    rsi2: float | None
    dist20: float | None
    fwd1: float
    fwd5: float
    fwd20: float


class StrategyResult(TypedDict):
    label: str
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    exposure_pct: float
    invested_blocks: int
    total_blocks: int


class BandSummary(TypedDict):
    band: str
    n: int
    mean: float
    median: float
    hit_rate: float
    std: float


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


def _mean(xs: Iterable[float]) -> float:
    vals = list(xs)
    return sum(vals) / len(vals) if vals else float("nan")


def _median(xs: Iterable[float]) -> float:
    vals = sorted(xs)
    if not vals:
        return float("nan")
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def _std(xs: Iterable[float]) -> float:
    vals = list(xs)
    if len(vals) < 2:
        return float("nan")
    avg = _mean(vals)
    return math.sqrt(sum((x - avg) ** 2 for x in vals) / (len(vals) - 1))


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 3:
        return float("nan")
    a = xs[:n]
    b = ys[:n]
    ma = _mean(a)
    mb = _mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return cov / math.sqrt(va * vb) if va and vb else float("nan")


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(_rank(xs), _rank(ys))


def max_drawdown(equity: list[float]) -> float:
    if not equity:
        return float("nan")
    peak = equity[0]
    mdd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            mdd = min(mdd, value / peak - 1)
    return mdd


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


def band_rows(rows: list[BacktestRow]) -> list[BandSummary]:
    out: list[BandSummary] = []
    for band in DECISION_ORDER:
        vals = [r["fwd5"] for r in rows if r["decision"] == band]
        if not vals:
            continue
        out.append({
            "band": band,
            "n": len(vals),
            "mean": _mean(vals),
            "median": _median(vals),
            "hit_rate": 100 * sum(1 for x in vals if x > 0) / len(vals),
            "std": _std(vals),
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
    return [
        strategy(rows, f"Score >= {FULL_RISK_MIN} (CONSTRUCTIVE+)",
                 lambda r: r["total"] >= FULL_RISK_MIN),
        strategy(rows, f"Score >= {ENGAGE_MIN} (SELECTIVE+)",
                 lambda r: r["total"] >= ENGAGE_MIN),
        strategy(rows, "Buy & hold", lambda r: True),
    ]


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
    engage = headline_strategies[1]
    buy_hold = headline_strategies[2]
    headline_label = (
        f"Validation window ({headline_rows[0]['date']} to {headline_rows[-1]['date']})"
        if validation_strategies else "Full sample"
    )

    lines = [
        "# Backtest Report",
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
        "| Band | Days | Mean | Median | Hit Rate | Std Dev |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for band in bands:
        lines.append(
            f"| {band['band']} | {band['n']:,} | {_fmt_pct(band['mean'])} | "
            f"{_fmt_pct(band['median'])} | {band['hit_rate']:.1f}% | {band['std']:.2f}% |"
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
        "Non-overlapping 5-trading-day holds. A strategy is long SPY for the next block only when the score clears its threshold.",
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
        "- No trading costs, slippage, taxes, or execution delays.",
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
