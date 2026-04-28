"""
analysis.py — Trading Desk Roundtable

Five distinct voices, each with a narrow remit, followed by a synthesis
from the Desk Head. Rule-based — fast, deterministic, no API key.

Each persona returns:
  { persona, role, avatar, stance, stance_color, read, points, verdict }

Call `roundtable(dashboard)` to get the full ordered list.
"""

from __future__ import annotations
import time


def _pick_stance(score: int) -> tuple[str, str]:
    if score >= 75: return "Bullish",  "green"
    if score >= 60: return "Cautious", "yellow"
    if score >= 45: return "Defensive", "orange"
    return "Bearish", "red"


# ─── 1. The Technician ─────────────────────────────────────────────────────
def persona_technician(d: dict) -> dict:
    t = d["pillars"]["trend"]["details"]
    v = d["pillars"]["volatility"]["details"]
    score = d["pillars"]["trend"]["score"]
    stance, color = _pick_stance(score)

    ma_count = sum([t.get("above_20", False), t.get("above_50", False), t.get("above_200", False)])
    regime = t.get("regime", "Unknown")
    ath = t.get("ath_dist", 0) or 0
    rsi = t.get("rsi14")
    spy_chg = t.get("spy_change_pct", 0) or 0

    # Opening read
    if ma_count == 3 and regime == "Uptrend":
        read = f"Full bull stack — SPY above 20/50/200. This is an environment for offense, not defense."
    elif ma_count == 2:
        read = f"Trend is repairing but not confirmed. Price above {ma_count}/3 majors — treat rallies with discipline, not conviction."
    elif ma_count == 1:
        read = f"Broken structure. Price below key MAs. Longs are against the tape here."
    else:
        read = f"All three MAs rolling over. This is a bear market in SPY until proven otherwise."

    points = []

    # RSI commentary
    if rsi is not None:
        if rsi >= 75:
            points.append({"icon": "🔴", "text": f"RSI {rsi} — severely overbought. Mean reversion risk is elevated; don't chase."})
        elif rsi >= 70:
            points.append({"icon": "⚠️", "text": f"RSI {rsi} — overbought. Wait for pullback to 20d before adding."})
        elif rsi <= 30:
            points.append({"icon": "✅", "text": f"RSI {rsi} — oversold. Look for failed breakdown → reversal setups."})
        elif 45 <= rsi <= 60:
            points.append({"icon": "✅", "text": f"RSI {rsi} — neutral with room to run either direction."})

    # ATH distance
    if ath >= -1:
        points.append({"icon": "⚠️", "text": f"SPY {ath:+.1f}% from 52W high — breakout zone, but chasing extended moves is where capital goes to die."})
    elif ath >= -5:
        points.append({"icon": "✅", "text": f"SPY {ath:+.1f}% from high — healthy consolidation, textbook re-entry zone."})
    elif ath >= -10:
        points.append({"icon": "⚠️", "text": f"SPY {ath:+.1f}% from high — correction territory, wait for reclaim of key levels."})
    else:
        points.append({"icon": "🔴", "text": f"SPY {ath:+.1f}% from high — significant drawdown. Capital preservation first."})

    # SPY today
    if spy_chg >= 1.5:
        points.append({"icon": "⚠️", "text": f"SPY {spy_chg:+.2f}% — strong move, but don't chase the close. Wait for an intraday pullback."})
    elif spy_chg <= -1.5:
        points.append({"icon": "🔴", "text": f"SPY {spy_chg:+.2f}% — wide-range down day. Let it settle before probing longs."})

    # Closing verdict
    if score >= 75:
        verdict = "Trade the trend. A+ setups on pullbacks to 20d."
    elif score >= 55:
        verdict = "Selective longs only. No breakouts into resistance."
    else:
        verdict = "Stand aside. Trends don't resume until MAs flip."

    return {
        "persona": "The Technician",
        "role": "Chart-reading · MAs · RSI · Regime",
        "avatar": "📊",
        "stance": stance, "stance_color": color,
        "read": read,
        "points": points,
        "verdict": verdict,
    }


# ─── 2. The Macro Strategist ───────────────────────────────────────────────
def persona_macro(d: dict) -> dict:
    m = d["pillars"]["macro"]["details"]
    score = d["pillars"]["macro"]["score"]
    stance, color = _pick_stance(score)

    tnx = m.get("tnx_value")
    yield_dir = m.get("yield_direction", "Flat")
    yield_label = m.get("yield_label", "Neutral")
    dxy_label = m.get("dxy_label", "Neutral")
    btc_trend = m.get("btc_trend", "N/A")
    btc_from_high = m.get("btc_from_high")
    fomc_days = m.get("fomc_days")
    fomc_date = m.get("fomc_date")

    # Opening read
    if tnx is None:
        read = "Macro inputs offline — flying without instruments. Size down until yields print."
    elif yield_dir == "Falling" and dxy_label == "Weakening":
        read = f"Both yields ({tnx:.2f}%) and dollar rolling over — pure liquidity tailwind. Growth and small caps get the bid."
    elif yield_dir == "Rising" and dxy_label == "Strengthening":
        read = f"Yields {yield_dir.lower()}, dollar {dxy_label.lower()} — classic risk-off combo. Growth and EM take the hit first."
    elif yield_dir == "Rising":
        read = f"10Y at {tnx:.2f}% and rising — duration-sensitive names are a short until the move stalls."
    else:
        read = f"Macro is mixed. 10Y {tnx:.2f}% ({yield_label}), DXY {dxy_label}. Don't trade macro conviction — trade what's moving."

    points = []

    # Yield detail
    if tnx is not None:
        if tnx < 3.5:
            points.append({"icon": "✅", "text": f"10Y {tnx:.2f}% — financial conditions easy. Multiples can expand here."})
        elif tnx < 4.0:
            points.append({"icon": "✅", "text": f"10Y {tnx:.2f}% — comfortable zone for equities."})
        elif tnx < 4.5:
            points.append({"icon": "⚠️", "text": f"10Y {tnx:.2f}% — neutral; watch 4.50 as the line in the sand."})
        elif tnx < 5.0:
            points.append({"icon": "⚠️", "text": f"10Y {tnx:.2f}% — restrictive. Small cap and unprofitable growth struggle."})
        else:
            points.append({"icon": "🔴", "text": f"10Y {tnx:.2f}% — this is where things break. Risk-off tail scenarios live here."})

    # DXY
    if dxy_label == "Weakening":
        points.append({"icon": "✅", "text": "Dollar weakening — supports multinationals, commodities, EM."})
    elif dxy_label == "Strengthening":
        points.append({"icon": "⚠️", "text": "Dollar strengthening — headwind for MNCs, commodities, and risk assets broadly."})

    # BTC as liquidity
    if btc_trend == "Full Bull":
        points.append({"icon": "✅", "text": f"BTC in full bull ({btc_from_high:+.1f}% from high) — liquidity is flowing, risk appetite intact."})
    elif btc_trend == "Bear":
        points.append({"icon": "🔴", "text": f"BTC trending down ({btc_from_high:+.1f}% from high) — liquidity is tightening at the margin."})
    elif btc_trend == "Recovering":
        points.append({"icon": "⚠️", "text": "BTC recovering but below 200d — liquidity repairing, not yet restored."})

    # FOMC proximity — THIS IS THE BIG ONE
    if fomc_days is not None:
        if fomc_days == 0:
            points.append({"icon": "🔴", "text": "FOMC is TODAY. Markets typically pin and then range-break. Don't hold size into 2:00 ET."})
        elif fomc_days == 1:
            points.append({"icon": "🔴", "text": f"FOMC TOMORROW ({fomc_date}). Positioning is frozen; most edges disappear into the print."})
        elif fomc_days <= 3:
            points.append({"icon": "⚠️", "text": f"FOMC in {fomc_days} days ({fomc_date}). Reduce size; exits get messy into the meeting."})
        elif fomc_days <= 7:
            points.append({"icon": "⚠️", "text": f"FOMC in {fomc_days} days ({fomc_date}). Still tradeable but start planning the exit."})

    # Closing verdict
    if score >= 70 and (fomc_days is None or fomc_days > 7):
        verdict = "Macro tailwind + clean calendar. Press the bid."
    elif fomc_days is not None and fomc_days <= 3:
        verdict = "Event risk dominates. Trade small or sit out."
    elif score >= 55:
        verdict = "Neutral macro. Don't let it veto a good setup."
    else:
        verdict = "Macro is against you. Respect it."

    return {
        "persona": "The Macro Strategist",
        "role": "Yields · Dollar · Liquidity · Fed",
        "avatar": "🌐",
        "stance": stance, "stance_color": color,
        "read": read,
        "points": points,
        "verdict": verdict,
    }


# ─── 3. The Risk Manager ───────────────────────────────────────────────────
def persona_risk(d: dict) -> dict:
    v = d["pillars"]["volatility"]["details"]
    b = d["pillars"]["breadth"]["details"]
    score = d["pillars"]["volatility"]["score"]
    stance, color = _pick_stance(score)

    vix = v.get("vix_level")
    vix_label = v.get("vix_label", "N/A")
    vix_trend = v.get("vix_trend", "Flat")
    vix_pctile = v.get("vix_pctile", 50)
    flow_score = v.get("flow_score", 50)
    flow_label = v.get("flow_label", "Neutral")
    rsp_vs_spy = b.get("rsp_vs_spy", 0) or 0
    sectors_pos = b.get("sectors_positive", 0)
    sectors_tot = b.get("sectors_total", 11)

    # Opening read
    if vix is None:
        read = "No vol data — assume the worst case until it's back."
    elif vix < 13 and flow_score >= 70:
        read = f"VIX {vix:.1f}, flow is euphoric. This is where complacency bites. Size down, not up."
    elif vix < 15:
        read = f"VIX {vix:.1f} ({vix_label}) — calm tape. Good for swing work, but don't mistake quiet for safe."
    elif vix < 20:
        read = f"VIX {vix:.1f} — normal operating range. Standard size, standard stops."
    elif vix < 28:
        read = f"VIX {vix:.1f} — elevated. Widen stops or cut size in half, pick one."
    else:
        read = f"VIX {vix:.1f} — panic zone. Either stand aside or hunt for capitulation bounces only."

    points = []

    # VIX percentile
    if vix_pctile <= 20:
        points.append({"icon": "⚠️", "text": f"VIX at {vix_pctile}th %ile of the year — cheap hedges, but a warning bell too."})
    elif vix_pctile >= 80:
        points.append({"icon": "✅", "text": f"VIX at {vix_pctile}th %ile — stress priced in, contrarian long window often here."})

    # Flow sentiment
    if flow_score >= 80:
        points.append({"icon": "⚠️", "text": f"Flow Sentiment {flow_score}/100 ({flow_label}) — crowd is all-in. Fade-the-last-buyer risk."})
    elif flow_score <= 25:
        points.append({"icon": "✅", "text": f"Flow Sentiment {flow_score}/100 ({flow_label}) — max pessimism, contrarian long territory."})
    elif 45 <= flow_score <= 65:
        points.append({"icon": "✅", "text": f"Flow Sentiment {flow_score}/100 — healthy middle ground, no extremes to fade."})

    # VIX trending signal
    if vix_trend == "Spiking":
        points.append({"icon": "🔴", "text": "VIX spiking intraday — something is breaking. Reduce exposure first, ask questions later."})
    elif vix_trend == "Falling" and vix and vix < 20:
        points.append({"icon": "✅", "text": "VIX falling into a calm tape — green light for trend continuation."})

    # Breadth divergence — the classic risk signal
    if rsp_vs_spy < -0.4:
        points.append({"icon": "⚠️", "text": f"RSP lagging SPY by {abs(rsp_vs_spy):.2f}% — mega-caps masking weakness underneath. Narrow rallies die young."})
    elif sectors_pos <= 4:
        points.append({"icon": "🔴", "text": f"Only {sectors_pos}/{sectors_tot} sectors positive — breadth is rolling, don't trust the index."})

    # Closing verdict
    if vix and vix < 15 and flow_score >= 75:
        verdict = "Complacency risk is my concern. Hedge cheap."
    elif vix and vix >= 25:
        verdict = "Volatility is in charge. Small size, tight stops, or nothing."
    elif score >= 65:
        verdict = "Green light. Standard risk budget applies."
    else:
        verdict = "Amber light. Half-size everything until signals clear."

    return {
        "persona": "The Risk Manager",
        "role": "Volatility · Sentiment · Drawdown",
        "avatar": "🛡",
        "stance": stance, "stance_color": color,
        "read": read,
        "points": points,
        "verdict": verdict,
    }


# ─── 4. The Sector Rotator ─────────────────────────────────────────────────
def persona_rotator(d: dict) -> dict:
    m = d["pillars"]["momentum"]["details"]
    b = d["pillars"]["breadth"]["details"]
    score = d["pillars"]["momentum"]["score"]
    stance, color = _pick_stance(score)

    leader = m.get("leader", {}) or {}
    laggard = m.get("laggard", {}) or {}
    participation = m.get("participation", "Unknown")
    rsp_vs_spy = m.get("rsp_vs_spy", 0) or 0
    iwm_vs_spy = m.get("iwm_vs_spy", 0) or 0
    n_pos = m.get("sectors_positive", 0)
    n_tot = m.get("sectors_total", 11)
    growth = m.get("growth_leaders", 0)

    sector_data = b.get("sector_data", {}) or {}
    industry_data = b.get("industry_data", {}) or {}

    # Top / bottom industries (the actionable signal)
    all_sub = {**sector_data, **industry_data}
    sorted_sub = sorted(all_sub.items(), key=lambda x: x[1].get("change_pct", 0), reverse=True)
    top3 = sorted_sub[:3]
    bot3 = sorted_sub[-3:]

    # Opening read
    if participation == "Broad" and growth >= 2:
        read = f"Broad participation + growth leading. This is the kind of tape that makes winners out of mediocre entries."
    elif participation == "Narrow":
        read = f"Narrow tape — {n_pos}/{n_tot} sectors holding. Index is up only because a handful of names are doing the work."
    elif iwm_vs_spy > 0.4:
        read = f"Small caps leading mega-caps by {iwm_vs_spy:+.2f}% — textbook risk-on rotation, chase the lagging winners."
    else:
        read = f"Rotation is active — leader {leader.get('name')} ({leader.get('change_pct', 0):+.2f}%), laggard {laggard.get('name')} ({laggard.get('change_pct', 0):+.2f}%). Follow the money."

    points = []

    # Top tickers
    if top3:
        top_str = ", ".join(f"{name}" + f" ({v['change_pct']:+.2f}%)" for name, v in [(v['name'], v) for _, v in top3])
        points.append({"icon": "🎯", "text": f"HUNT HERE: {top_str}"})

    # Bottom tickers
    if bot3:
        bot_str = ", ".join(f"{v['name']} ({v['change_pct']:+.2f}%)" for _, v in bot3)
        points.append({"icon": "⛔", "text": f"AVOID: {bot_str}"})

    # Equal-weight signal
    if rsp_vs_spy > 0.3:
        points.append({"icon": "✅", "text": f"RSP outperforming SPY by {rsp_vs_spy:+.2f}% — broad rotation, average stock is working."})
    elif rsp_vs_spy < -0.3:
        points.append({"icon": "⚠️", "text": f"RSP lagging SPY by {abs(rsp_vs_spy):.2f}% — top-heavy rally, only mega-caps working."})

    # Small caps
    if iwm_vs_spy > 0.4:
        points.append({"icon": "✅", "text": f"IWM leading by {iwm_vs_spy:+.2f}% — speculative appetite is back, reaching further out the risk curve."})
    elif iwm_vs_spy < -0.4:
        points.append({"icon": "⚠️", "text": f"IWM lagging by {abs(iwm_vs_spy):.2f}% — defensive rotation, risk-off under the surface."})

    # Closing verdict
    if participation == "Broad" and growth >= 2:
        verdict = f"Rotate into {leader.get('name', 'leaders')}. Follow, don't predict."
    elif participation == "Narrow":
        verdict = "Stay out of laggards. Only trade confirmed leaders with volume."
    else:
        verdict = f"Leader is {leader.get('name', '—')} — that's your shopping list."

    return {
        "persona": "The Sector Rotator",
        "role": "Leadership · Laggards · Rotation",
        "avatar": "🔄",
        "stance": stance, "stance_color": color,
        "read": read,
        "points": points,
        "verdict": verdict,
    }


# ─── 5. The Desk Head (synthesis) ──────────────────────────────────────────
def persona_desk_head(d: dict, others: list[dict]) -> dict:
    total = d.get("total_score", 0)
    decision = d.get("decision", "—")
    pos_size = d.get("position_size", "—")
    stance, color = _pick_stance(total)

    # Count stances from other personas
    stances = [p["stance"] for p in others]
    bulls = stances.count("Bullish")
    bears = sum(1 for s in stances if s in ("Bearish", "Defensive"))
    cautious = stances.count("Cautious")

    m = d["pillars"]["macro"]["details"]
    fomc_days = m.get("fomc_days")
    v = d["pillars"]["volatility"]["details"]
    vix = v.get("vix_level") or 20
    t = d["pillars"]["trend"]["details"]
    above_200 = t.get("above_200", False)

    # Opening read — reconcile the desk
    if bulls >= 3 and bears == 0:
        read = f"Desk is aligned long. {bulls}/4 analysts bullish, zero bears. Conditions rarely get this clean — press size."
    elif bears >= 3:
        read = f"Desk is aligned defensive. {bears}/4 analysts negative. Capital preservation trumps opportunity cost here."
    elif bulls >= 2 and bears <= 1:
        read = f"Desk leans constructive but not unanimous — {bulls} bulls, {cautious} cautious, {bears} defensive. Trade it, but don't force it."
    elif bulls == bears:
        read = "Split desk. That usually means chop. Smallest setups only, or sit on hands."
    else:
        read = f"Mixed picture — {bulls} bullish, {cautious} cautious, {bears} defensive. This is selectivity weather."

    points = []
    points.append({"icon": "🎯", "text": f"VERDICT: {decision} · Score {total}/100 · {pos_size}"})

    # Key risk call-out
    if fomc_days is not None and fomc_days <= 3:
        points.append({"icon": "🔴", "text": f"FOMC IN {fomc_days} DAYS — this overrides everything else. Cut size now."})
    elif vix >= 25:
        points.append({"icon": "⚠️", "text": "Elevated vol — realized and implied both up. Risk budget shrinks mechanically."})
    elif not above_200:
        points.append({"icon": "⚠️", "text": "SPY below 200d — bear-market rules apply. Quick in, quick out."})

    # Execution rule — the single most important output
    if total >= 80 and vix < 20 and (fomc_days is None or fomc_days > 7):
        rule = "Full size on A/B+ setups. Add on intraday pullbacks to 20d. No breakouts at the highs."
    elif total >= 65 and (fomc_days is None or fomc_days > 3):
        rule = "Half size only. A+ setups with clean pullback entries. Stops at the breakout level."
    elif total >= 50 and above_200:
        rule = "Quarter size max. Tightest stops. Take profits at first resistance — no let-it-run."
    elif fomc_days is not None and fomc_days <= 3:
        rule = "Flat into FOMC. Any new positions must close before 2:00 ET Wednesday."
    else:
        rule = "Stand aside. No new longs. Watch levels — patience is a position."

    points.append({"icon": "⚡", "text": f"EXECUTION: {rule}"})

    # Final line
    if total >= 75:
        verdict = "Good tape. Don't overthink it."
    elif total >= 60:
        verdict = "Be patient. One A+ trade beats five B trades."
    elif total >= 45:
        verdict = "Skeptical participation only."
    else:
        verdict = "Cash is a position. Preserve capital."

    return {
        "persona": "The Desk Head",
        "role": "Synthesis · Final call · Execution",
        "avatar": "🎯",
        "stance": stance, "stance_color": color,
        "read": read,
        "points": points,
        "verdict": verdict,
    }


# ─── public entry ──────────────────────────────────────────────────────────
def roundtable(dashboard: dict) -> dict:
    """Full trading desk output. Ordered: specialists first, Desk Head last."""
    tech = persona_technician(dashboard)
    macro = persona_macro(dashboard)
    risk = persona_risk(dashboard)
    rot = persona_rotator(dashboard)
    head = persona_desk_head(dashboard, [tech, macro, risk, rot])
    return {
        "personas": [tech, macro, risk, rot, head],
        "timestamp": time.strftime("%H:%M UTC", time.gmtime()),
    }
