"""test_scoring.py — Unit tests for the 5-pillar market scoring engine.

Each pillar function (score_volatility, score_trend, score_breadth,
score_momentum, score_macro) is a pure function of mock quotes + closes —
no network access needed.  All data-layer imports are stubbed out before
importing scoring so these tests run fully offline.

Run with:  python3 test_scoring.py
"""

from __future__ import annotations
import os
import sys
import types

# ── stub the data module so scoring.py imports cleanly without network calls ──
_data_stub = types.ModuleType("data")
for _fn in [
    "get_quote", "get_history", "get_ohlcv", "btc_quote", "btc_history",
    "market_state", "fomc_proximity", "econ_proximity",
    "fetch_fear_greed_stock", "fetch_fear_greed_crypto",
    "opex_proximity", "seasonality", "earnings_season", "fetch_futures_tape",
]:
    setattr(_data_stub, _fn, lambda *a, **kw: None)
sys.modules["data"] = _data_stub

sys.path.insert(0, os.path.dirname(__file__))
import scoring  # noqa: E402  (must come after stub)

# ─── helpers ─────────────────────────────────────────────────────────────────

def q(px: float, chg: float = 0.5) -> dict:
    """Minimal mock quote dict mirroring the real yfinance payload keys."""
    return {"price": px, "changePct": chg}


def flat_closes(n: int = 252, val: float = 100.0) -> list[float]:
    """n identical closing prices — MAs == price, RSI ~50."""
    return [float(val)] * n


def trending_closes(n: int = 252, start: float = 100.0,
                    per_day: float = 0.3) -> list[float]:
    """Monotonically rising (per_day > 0) or falling (per_day < 0) closes."""
    return [round(start + per_day * i, 4) for i in range(n)]


_PASS = 0
_FAIL = 0


def ok(label: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        print(f"  ✓ {label}")
        _PASS += 1
    else:
        print(f"  ✗ {label}")
        _FAIL += 1


def between(val, lo, hi) -> bool:
    return lo <= val <= hi


# ─── pillar 1: score_volatility ───────────────────────────────────────────────

def test_volatility() -> None:
    print("\n[score_volatility]")

    # Low VIX, calm flow → high score
    vix_history = flat_closes(252, 12.0)
    quotes_calm = {
        "^VIX":  q(12.0, -2.0),
        "TQQQ":  q(40.0,  3.0),
        "SQQQ":  q(10.0, -4.0),
        "UVXY":  q(5.0,  -6.0),
    }
    r = scoring.score_volatility(quotes_calm, vix_history)
    ok("Low VIX → score > 60",          r["score"] > 60)
    ok("Low VIX → vix_label == 'Low'",  r["details"]["vix_label"] == "Low")
    ok("reasons list is non-empty",     bool(r["reasons"]))

    # Extreme VIX, spiking → low score
    quotes_fear = {
        "^VIX":  q(38.0,  8.0),
        "TQQQ":  q(40.0, -5.0),
        "SQQQ":  q(10.0,  6.0),
        "UVXY":  q(5.0,  12.0),
    }
    r2 = scoring.score_volatility(quotes_fear, flat_closes(252, 38.0))
    ok("Extreme VIX, spiking → score < 40", r2["score"] < 40)

    # Missing VIX → neutral 50 fallback
    r_empty = scoring.score_volatility({}, [])
    ok("No VIX → score == 50 (neutral)", r_empty["score"] == 50)

    # VIX percentile: VIX=40 vs history of 12s → 100th percentile
    r_pct = scoring.score_volatility({"^VIX": q(40.0, 2.0)}, flat_closes(252, 12.0))
    ok("VIX 40 vs history of 12s → vix_pctile == 100",
       r_pct["details"]["vix_pctile"] == 100)

    # Short history (<20 points) → vix_pctile is None (not enough data)
    r_short = scoring.score_volatility({"^VIX": q(20.0)}, flat_closes(10, 20.0))
    ok("< 20 history points → vix_pctile is None",
       r_short["details"]["vix_pctile"] is None)

    # VIX term structure — backwardation (VIX > VIX3M by >5%)
    quotes_bw = {
        "^VIX":   q(28.0, 3.0),
        "^VIX3M": q(24.0, 1.0),
        "TQQQ": q(40, -2), "SQQQ": q(10, 2), "UVXY": q(5, 0),
    }
    r_bw = scoring.score_volatility(quotes_bw, flat_closes(252, 25.0))
    ok("VIX 28 / VIX3M 24 (1.167x) → Backwardation",
       r_bw["details"]["vix_term_label"] == "Backwardation")

    # VIX term structure — steep contango (VIX3M >> VIX)
    quotes_ct = {
        "^VIX":   q(15.0, -1.0),
        "^VIX3M": q(18.0,  0.5),
        "TQQQ": q(40, 2), "SQQQ": q(10, -2), "UVXY": q(5, -3),
    }
    r_ct = scoring.score_volatility(quotes_ct, flat_closes(252, 15.0))
    ok("VIX 15 / VIX3M 18 (0.833x) → Steep Contango",
       r_ct["details"]["vix_term_label"] == "Steep Contango")

    # VIX9D fear spike (VIX9D > VIX)
    quotes_9d = {
        "^VIX":  q(20.0, 0.5),
        "^VIX9D": q(23.0, 2.0),
        "TQQQ": q(40, -1), "SQQQ": q(10, 1), "UVXY": q(5, 3),
    }
    r_9d = scoring.score_volatility(quotes_9d, flat_closes(252, 20.0))
    ok("VIX9D > VIX → vix9d_label == 'Fear Spike'",
       r_9d["details"]["vix9d_label"] == "Fear Spike")

    # VIX9D calm (VIX9D < 90% of VIX)
    quotes_9d_calm = {
        "^VIX":  q(22.0, -0.5),
        "^VIX9D": q(18.0, -1.0),
        "TQQQ": q(40, 1), "SQQQ": q(10, -1), "UVXY": q(5, -2),
    }
    r_9d_c = scoring.score_volatility(quotes_9d_calm, flat_closes(252, 22.0))
    ok("VIX9D 18 / VIX 22 (0.818x) → vix9d_label == 'Calm'",
       r_9d_c["details"]["vix9d_label"] == "Calm")

    # SKEW ≥ 150 → Extreme Tail Risk
    quotes_skew = {
        "^VIX": q(18.0, 0.0), "^SKEW": q(152.0),
        "TQQQ": q(40, 0.5), "SQQQ": q(10, -0.5), "UVXY": q(5, -1),
    }
    r_skew = scoring.score_volatility(quotes_skew, flat_closes(252, 18.0))
    ok("SKEW 152 → skew_label == 'Extreme Tail Risk'",
       r_skew["details"]["skew_label"] == "Extreme Tail Risk")

    # Score is always clamped 0–100
    ok("score clamped 0-100", between(r["score"], 0, 100))
    ok("score clamped 0-100 (fear case)", between(r2["score"], 0, 100))


# ─── pillar 2: score_trend ────────────────────────────────────────────────────

def test_trend() -> None:
    print("\n[score_trend]")

    # Rising closes → price well above 20d/50d/200d MA → Uptrend
    spy_up = trending_closes(252, start=100.0, per_day=0.5)   # ends ~225
    qqq_up = trending_closes(252, start=200.0, per_day=0.5)
    quotes_up = {"SPY": q(spy_up[-1], 0.8), "QQQ": q(qqq_up[-1], 0.9)}
    r_up = scoring.score_trend(quotes_up, spy_up, qqq_up)
    ok("Rising SPY above all MAs → regime == 'Uptrend'",
       r_up["details"]["regime"] == "Uptrend")
    ok("Uptrend → score > 70", r_up["score"] > 70)

    # Falling closes → price below all MAs → Downtrend
    spy_dn = trending_closes(252, start=300.0, per_day=-0.5)  # ends ~175
    qqq_dn = trending_closes(252, start=300.0, per_day=-0.5)
    quotes_dn = {"SPY": q(spy_dn[-1], -1.2), "QQQ": q(qqq_dn[-1], -1.1)}
    r_dn = scoring.score_trend(quotes_dn, spy_dn, qqq_dn)
    ok("Falling SPY below all MAs → regime == 'Downtrend'",
       r_dn["details"]["regime"] == "Downtrend")
    ok("Downtrend → score < 30", r_dn["score"] < 30)

    # Empty input → no crash, returns valid dict
    r_empty = scoring.score_trend({}, [], [])
    ok("Empty input → no crash", "score" in r_empty)
    ok("Empty input → score is int/float", isinstance(r_empty["score"], (int, float)))

    # Monotonically rising closes → RSI should be elevated (≥70)
    mono = trending_closes(252, 50.0, 1.0)
    quotes_ob = {"SPY": q(mono[-1], 0.5), "QQQ": q(mono[-1], 0.5)}
    r_ob = scoring.score_trend(quotes_ob, mono, mono)
    ok("Monotonically rising → RSI ≥ 70",
       (r_ob["details"]["rsi14"] or 0) >= 70)
    ok("Overbought RSI reduces score below perfect MA score",
       r_ob["score"] < 100)

    # details contains all expected keys
    expected_keys = {"regime", "regime_color", "above_20", "above_50", "above_200", "rsi14"}
    ok("details has all required keys", expected_keys.issubset(r_up["details"].keys()))

    # score always clamped
    ok("score clamped 0-100 (up)", between(r_up["score"], 0, 100))
    ok("score clamped 0-100 (down)", between(r_dn["score"], 0, 100))


# ─── pillar 3: score_breadth ──────────────────────────────────────────────────

def test_breadth() -> None:
    print("\n[score_breadth]")

    # All sectors positive, RSP in uptrend → strong breadth
    rsp_up = trending_closes(252, 80.0, 0.15)
    rsp_px = rsp_up[-1]
    quotes_broad = {"RSP": q(rsp_px, 1.0), "SPY": q(450.0, 0.8)}
    for sym in scoring.SECTOR_SYMBOLS + scoring.INDUSTRY_SYMBOLS:
        quotes_broad[sym] = q(100.0, 1.5)
    r_broad = scoring.score_breadth(quotes_broad, rsp_up)
    ok("All 11 sectors positive → sectors_positive == 11",
       r_broad["details"]["sectors_positive"] == 11)
    ok("Broad breadth → score ≥ 50", r_broad["score"] >= 50)
    ok("RSP above 50d → rsp_above_50 is True",
       r_broad["details"]["rsp_above_50"] is True)

    # All sectors negative, RSP in downtrend → poor breadth
    rsp_dn = trending_closes(252, 120.0, -0.3)
    rsp_px2 = rsp_dn[-1]
    quotes_narrow = {"RSP": q(rsp_px2, -1.0), "SPY": q(450.0, -0.5)}
    for sym in scoring.SECTOR_SYMBOLS + scoring.INDUSTRY_SYMBOLS:
        quotes_narrow[sym] = q(100.0, -1.5)
    r_narrow = scoring.score_breadth(quotes_narrow, rsp_dn)
    ok("All sectors negative → sectors_positive == 0",
       r_narrow["details"]["sectors_positive"] == 0)
    ok("Narrow breadth → score < 20", r_narrow["score"] < 20)

    # sector_histories: all sectors above 200d MA → pct == 100
    sector_hists = {s: trending_closes(252, 100.0, 0.2) for s in scoring.SECTOR_SYMBOLS}
    rsp_up2 = trending_closes(252, 80.0, 0.1)
    rsp_px3 = rsp_up2[-1]
    quotes_hist = {"RSP": q(rsp_px3, 0.5), "SPY": q(450.0, 0.3)}
    for sym in scoring.SECTOR_SYMBOLS + scoring.INDUSTRY_SYMBOLS:
        quotes_hist[sym] = q(100.0, 0.5)
    r_hist = scoring.score_breadth(quotes_hist, rsp_up2, sector_histories=sector_hists)
    ok("All rising sector histories → pct_sectors_above_200 == 100",
       r_hist["details"]["pct_sectors_above_200"] == 100)
    ok("100% above 200d → score > 60", r_hist["score"] > 60)

    # No sector quotes → still returns valid structure
    r_bare = scoring.score_breadth({"RSP": q(100, 0), "SPY": q(450, 0)},
                                   flat_closes(252, 100.0))
    ok("No sector quotes → valid dict", "score" in r_bare)

    # score clamped
    ok("score clamped 0-100", between(r_broad["score"], 0, 100))
    ok("score clamped 0-100 (narrow)", between(r_narrow["score"], 0, 100))


# ─── pillar 4: score_momentum ─────────────────────────────────────────────────

def test_momentum() -> None:
    print("\n[score_momentum]")

    # Risk-on: RSP > SPY, IWM leading, all growth sectors positive
    quotes_on = {
        "SPY": q(450.0,  0.5),
        "RSP": q(160.0,  1.2),   # RSP outperforms → broad rally
        "QQQ": q(400.0,  1.0),
        "IWM": q(200.0,  1.8),   # small caps leading → risk-on
        "HYG": q(80.0,   0.3),
    }
    for sym in scoring.SECTOR_SYMBOLS:
        quotes_on[sym] = q(100.0, 1.2)
    r_on = scoring.score_momentum(quotes_on)
    ok("Risk-on setup → score > 50",            r_on["score"] > 50)
    ok("RSP > SPY → rsp_outperforming is True", r_on["details"]["rsp_outperforming"] is True)

    # Risk-off: RSP < SPY, IWM lagging, growth negative
    quotes_off = {
        "SPY": q(450.0,  0.3),
        "RSP": q(160.0, -0.5),   # RSP lags → narrow market
        "QQQ": q(400.0, -0.2),
        "IWM": q(200.0, -1.5),   # small caps lagging → risk-off
        "HYG": q(80.0,  -0.8),
    }
    for sym in scoring.SECTOR_SYMBOLS:
        quotes_off[sym] = q(100.0, -0.5)
    r_off = scoring.score_momentum(quotes_off)
    ok("Risk-off setup → score < 50",             r_off["score"] < 50)
    ok("RSP < SPY → rsp_outperforming is False",  r_off["details"]["rsp_outperforming"] is False)

    # Returns all required keys
    ok("Returns score/details/reasons",
       all(k in r_on for k in ("score", "details", "reasons")))
    ok("score clamped 0-100", between(r_on["score"], 0, 100))
    ok("score clamped 0-100 (off)", between(r_off["score"], 0, 100))

    # Sector RS with sector_histories (cyclicals leading → +5)
    sector_hists = {s: trending_closes(252, 100.0, 0.2) for s in scoring.SECTOR_SYMBOLS}
    r_rs = scoring.score_momentum(quotes_on, sector_histories=sector_hists)
    ok("sector_histories provided → sector_rs list populated",
       isinstance(r_rs["details"]["sector_rs"], list))


# ─── pillar 5: score_macro ────────────────────────────────────────────────────

def test_macro() -> None:
    print("\n[score_macro]")

    fomc_far = {"days_until": 30, "date": "2026-06-17", "label": "30d to FOMC", "color": "green"}
    fomc_near = {"days_until": 1,  "date": "2026-05-20", "label": "FOMC Tomorrow", "color": "red"}

    # Bullish macro: yields falling, DXY weakening, FOMC far away
    tnx_falling = trending_closes(30, start=4.8, per_day=-0.02)   # trending down
    dxy_falling = trending_closes(30, start=107.0, per_day=-0.1)  # DXY weakening
    quotes_bull = {
        "^TNX":      q(4.2, -2.0),
        "DX-Y.NYB":  q(104.0, -0.5),
        "TLT":       q(95.0, 0.7),
        "HYG":       q(80.0, 0.4),
        "GLD":       q(190.0, 0.2),
        "SPY":       q(455.0, 0.6),
    }
    r_bull = scoring.score_macro(quotes_bull, tnx_falling, dxy_falling,
                                  btc_q=None, btc_closes=[],
                                  fomc=fomc_far)
    ok("Bullish macro → score ≥ 50", r_bull["score"] >= 50)
    ok("Returns score/details/reasons",
       all(k in r_bull for k in ("score", "details", "reasons")))

    # Bearish macro: yields spiking, DXY surging, FOMC tomorrow
    tnx_rising = trending_closes(30, start=4.0, per_day=0.05)
    dxy_rising  = trending_closes(30, start=103.0, per_day=0.1)
    quotes_bear = {
        "^TNX":      q(5.5, 3.0),
        "DX-Y.NYB":  q(110.0, 1.2),
        "TLT":       q(85.0, -0.6),
        "HYG":       q(75.0, -1.2),
        "GLD":       q(195.0, -0.2),
        "SPY":       q(440.0, -0.8),
    }
    r_bear = scoring.score_macro(quotes_bear, tnx_rising, dxy_rising,
                                  btc_q=None, btc_closes=[],
                                  fomc=fomc_near)
    ok("Bearish macro + FOMC tomorrow → score ≤ 55", r_bear["score"] <= 55)
    ok("FOMC in 1d → '-15 FOMC' reason present",
       any("FOMC" in reason for reason in r_bear["reasons"]))

    # Yield curve: inverted (^IRX > ^TNX)
    quotes_inv = dict(quotes_bull)
    quotes_inv["^IRX"] = q(5.2)   # 3-month > 10-year → inversion
    r_inv = scoring.score_macro(quotes_inv, tnx_falling, dxy_falling,
                                 btc_q=None, btc_closes=[], fomc=fomc_far)
    ok("^IRX > ^TNX → yield curve inverted in reasons",
       any("Inverted" in r or "inversion" in r.lower() for r in r_inv["reasons"]))

    # BTC in full bull adds positive score contribution
    btc_up = trending_closes(252, 30000.0, 100.0)
    btc_q_bull = q(btc_up[-1], 2.5)
    r_btc = scoring.score_macro(quotes_bull, tnx_falling, dxy_falling,
                                 btc_q=btc_q_bull, btc_closes=btc_up,
                                 fomc=fomc_far)
    ok("BTC full bull → score ≥ r_bull without BTC", r_btc["score"] >= r_bull["score"])

    # Empty input → no crash
    r_empty = scoring.score_macro({}, [], [], btc_q=None, btc_closes=[], fomc={})
    ok("Empty input → no crash", "score" in r_empty)
    ok("Empty input → score clamped 0-100", between(r_empty["score"], 0, 100))


# ─── utilities & constants ───────────────────────────────────────────────────

def test_utilities() -> None:
    print("\n[utilities & decision_for_score]")
    ok("clamp(-10) == 0",    scoring.clamp(-10) == 0)
    ok("clamp(110) == 100",  scoring.clamp(110) == 100)
    ok("clamp(55) == 55",    scoring.clamp(55) == 55)
    ok("clamp(0) == 0",      scoring.clamp(0) == 0)
    ok("clamp(100) == 100",  scoring.clamp(100) == 100)

    decision, color, position = scoring.decision_for_score(90)
    ok("score 90 → 'STRONG YES'", decision == "STRONG YES")

    decision, color, position = scoring.decision_for_score(72)
    ok("score 72 → 'YES'", decision == "YES")

    decision, color, position = scoring.decision_for_score(56)
    ok("score 56 → 'CAUTION'", decision == "CAUTION")

    decision, color, position = scoring.decision_for_score(20)
    ok("score 20 → contains 'WAIT' or 'NO'",
       "WAIT" in decision or "NO" in decision)

    ok("decision_for_score returns 3 values",
       len(scoring.decision_for_score(50)) == 3)


def test_constants() -> None:
    print("\n[named constants]")
    required = [
        "VIX_CALM", "VIX_MODERATE", "VIX_ELEVATED", "VIX_HIGH",
        "FLOW_NET_STRONG_BULL", "FLOW_NET_BULL", "FLOW_NET_MILD_BULL",
        "RSI_SEVERELY_OVERBOUGHT", "RSI_OVERBOUGHT", "RSI_OVERSOLD",
        "SKEW_EXTREME", "SKEW_ELEVATED",
    ]
    for name in required:
        ok(f"constant {name!r} exists", hasattr(scoring, name))

    # Sanity-check values are numeric and ordered
    ok("VIX_CALM < VIX_MODERATE < VIX_ELEVATED < VIX_HIGH",
       scoring.VIX_CALM < scoring.VIX_MODERATE
       < scoring.VIX_ELEVATED < scoring.VIX_HIGH)
    ok("RSI_OVERBOUGHT < RSI_SEVERELY_OVERBOUGHT",
       scoring.RSI_OVERBOUGHT < scoring.RSI_SEVERELY_OVERBOUGHT)


# ─── runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_volatility()
    test_trend()
    test_breadth()
    test_momentum()
    test_macro()
    test_utilities()
    test_constants()

    total = _PASS + _FAIL
    print(f"\n{'=' * 55}")
    print(f"Results: {_PASS}/{total} passed", end="")
    if _FAIL:
        print(f",  {_FAIL} FAILED  ←  see ✗ above")
    else:
        print("  ✓  ALL PASS")
    sys.exit(0 if _FAIL == 0 else 1)
