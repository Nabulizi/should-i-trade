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
    score = d["pillars"]["trend"]["score"]
    stance, color = _pick_stance(score)

    ma_count = sum([t.get("above_20", False), t.get("above_50", False), t.get("above_200", False)])
    regime = t.get("regime", "Unknown")
    ath = t.get("ath_dist", 0) or 0
    rsi = t.get("rsi14")
    spy_chg = t.get("spy_change_pct", 0) or 0
    macd_hist = t.get("macd_hist")
    macd_label = t.get("macd_label", "")
    char_label = t.get("char_label", "N/A")

    # Opening read — regime + market character
    if ma_count == 3 and char_label == "Trending":
        read = "Full bull stack + trending tape. This is an environment for offense — entries pull back clean and follow through."
    elif ma_count == 3 and char_label == "Choppy":
        read = "Full bull stack but the tape is choppy. Structure is intact; execution is hard. Stick to A+ pullbacks, skip intraday noise."
    elif ma_count == 3 and char_label == "Extended":
        read = "Full bull stack but SPY is extended. Regime says long; price says don't chase. Wait for the first pullback base."
    elif ma_count == 3:
        read = "Full bull stack — SPY above 20/50/200. This is an environment for offense, not defense."
    elif ma_count == 2:
        read = f"Trend is repairing but not confirmed. Price above {ma_count}/3 majors — treat rallies with discipline, not conviction."
    elif ma_count == 1:
        read = "Broken structure. Price below key MAs. Longs are against the tape here."
    else:
        read = "All three MAs rolling over. This is a bear market in SPY until proven otherwise."

    points = []

    # RSI
    if rsi is not None:
        if rsi >= 75:
            points.append({"icon": "🔴", "text": f"RSI {rsi} — severely overbought. Mean reversion risk elevated; don't chase."})
        elif rsi >= 70:
            points.append({"icon": "⚠️", "text": f"RSI {rsi} — overbought. Wait for pullback to 20d before adding."})
        elif rsi <= 30:
            points.append({"icon": "✅", "text": f"RSI {rsi} — oversold. Look for failed breakdown → reversal setups."})
        elif 45 <= rsi <= 60:
            points.append({"icon": "✅", "text": f"RSI {rsi} — sweet spot. Ideal swing entry zone; room to run."})
        else:
            points.append({"icon": "⚠️", "text": f"RSI {rsi} — no clean edge here. Wait for reset toward 45–60 before adding."})

    # MACD — label values from scoring engine are e.g. "Bullish (above 0)", "Bearish (below 0)"
    if macd_hist is not None:
        bull = macd_label.startswith("Bullish")
        bear = macd_label.startswith("Bearish")
        above_zero = "above 0" in macd_label
        if bull and above_zero:
            points.append({"icon": "✅", "text": f"MACD line and histogram both above zero ({macd_label}) — momentum confirming the trend."})
        elif bull and not above_zero:
            points.append({"icon": "⚠️", "text": f"MACD histogram positive but line still below zero ({macd_label}) — early recovery, not yet confirmed."})
        elif bear and above_zero:
            points.append({"icon": "⚠️", "text": f"MACD line above zero but histogram negative ({macd_label}) — momentum fading. Tighten stops."})
        elif bear and not above_zero:
            points.append({"icon": "🔴", "text": f"MACD line and histogram both below zero ({macd_label}) — no momentum tailwind. No new longs until crossover."})
        else:
            points.append({"icon": "⚪", "text": f"MACD {macd_label} — no clear signal."})

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

    # Closing verdict — incorporate character
    if score >= 75 and char_label == "Trending":
        verdict = "Trending tape. A/B+ pullbacks to 20d are the play — high follow-through probability."
    elif score >= 75:
        verdict = "Trade the trend. A+ setups on pullbacks to 20d."
    elif score >= 55:
        verdict = "Selective longs only. No breakouts into resistance."
    else:
        verdict = "Stand aside. Trends don't resume until MAs flip."

    return {
        "persona": "The Technician",
        "role": "Chart-reading · MAs · RSI · MACD · Character",
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
    dxy_chg = m.get("dxy_change_pct", 0) or 0
    btc_trend = m.get("btc_trend", "N/A")
    btc_from_high = m.get("btc_from_high")
    fomc_days = m.get("fomc_days")
    fomc_date = m.get("fomc_date")

    # Opening read — yield+DXY as a paired signal, not individual reads
    if tnx is None:
        read = "Macro inputs offline — flying without instruments. Size down until yields print."
    elif yield_dir == "Falling" and dxy_label == "Weakening":
        read = (f"10Y falling ({tnx:.2f}%) + dollar weakening — the clearest liquidity tailwind this framework sees. "
                "Growth names, small caps, and cyclicals get the bid. This is the environment to press size.")
    elif yield_dir == "Rising" and dxy_label == "Strengthening":
        read = (f"10Y rising ({tnx:.2f}%) + dollar strengthening simultaneously — textbook risk-off squeeze. "
                "Growth and EM get repriced first; defensives and cash earn a real return. Reduce duration exposure.")
    elif yield_dir == "Rising" and dxy_label == "Weakening":
        read = (f"10Y rising ({tnx:.2f}%) but dollar weakening — yields moving on growth expectations, not fear. "
                "Cyclicals can absorb this; it's the unprofitable growth and long-duration that struggles.")
    elif yield_dir == "Falling" and dxy_label == "Strengthening":
        read = (f"10Y falling ({tnx:.2f}%) but dollar strengthening — flight to quality signal. "
                "Something is bid underneath; watch whether equities hold or follow bonds lower.")
    else:
        read = (f"Macro is static. 10Y {tnx:.2f}% ({yield_label}), DXY {dxy_label}. "
                "No directional conviction from rates or dollar — trade what's moving, not the macro narrative.")

    points = []

    # Yield level — absolute threshold
    if tnx is not None:
        if tnx < 3.5:
            points.append({"icon": "✅", "text": f"10Y {tnx:.2f}% — financial conditions easy. Multiple expansion is possible here."})
        elif tnx < 4.0:
            points.append({"icon": "✅", "text": f"10Y {tnx:.2f}% — comfortable zone for equities. No yield-driven headwind."})
        elif tnx < 4.5:
            points.append({"icon": "⚠️", "text": f"10Y {tnx:.2f}% — neutral; 4.50 is the line. Above it, growth multiples compress."})
        elif tnx < 5.0:
            points.append({"icon": "⚠️", "text": f"10Y {tnx:.2f}% — restrictive. Small cap and unprofitable growth struggle mechanically."})
        else:
            points.append({"icon": "🔴", "text": f"10Y {tnx:.2f}% — this is where credit events and forced selling happen. Risk-off tail scenarios live here."})

    # DXY direction with magnitude
    if dxy_label == "Weakening" and abs(dxy_chg) >= 0.3:
        points.append({"icon": "✅", "text": f"Dollar down {abs(dxy_chg):.2f}% — tailwind for multinationals, commodities, and EM. Broadens the hunt list."})
    elif dxy_label == "Strengthening" and abs(dxy_chg) >= 0.3:
        points.append({"icon": "⚠️", "text": f"Dollar up {dxy_chg:+.2f}% — headwind for MNCs and risk assets. Narrows the hunt list to domestic US."})
    elif dxy_label == "Weakening":
        points.append({"icon": "✅", "text": "Dollar drifting lower — mild tailwind, not a strong signal on its own."})
    elif dxy_label == "Strengthening":
        points.append({"icon": "⚠️", "text": "Dollar drifting higher — mild headwind, worth monitoring but not a veto."})

    # BTC as liquidity proxy
    if btc_trend == "Full Bull":
        points.append({"icon": "✅", "text": f"BTC in full bull ({btc_from_high:+.1f}% from high) — liquidity is flowing, risk appetite intact."})
    elif btc_trend == "Bear":
        points.append({"icon": "🔴", "text": f"BTC trending down ({btc_from_high:+.1f}% from high) — liquidity tightening at the margin; watch for risk-off spillover."})
    elif btc_trend == "Recovering":
        points.append({"icon": "⚠️", "text": "BTC recovering but below 200d — liquidity repairing, not yet restored. Don't lean on it."})

    # FOMC proximity
    if fomc_days is not None:
        if fomc_days == 0:
            points.append({"icon": "🔴", "text": "FOMC is TODAY. Markets typically pin then range-break. Don't hold size into 2:00 ET."})
        elif fomc_days == 1:
            points.append({"icon": "🔴", "text": f"FOMC TOMORROW ({fomc_date}). Positioning is frozen; most edges disappear into the print."})
        elif fomc_days <= 3:
            points.append({"icon": "⚠️", "text": f"FOMC in {fomc_days} days ({fomc_date}). Reduce size; exits get messy into the meeting."})
        elif fomc_days <= 7:
            points.append({"icon": "⚠️", "text": f"FOMC in {fomc_days} days ({fomc_date}). Still tradeable — start planning the exit."})

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
    vix9d_ratio = v.get("vix9d_ratio")
    vix9d_label = v.get("vix9d_label", "N/A")
    skew_value = v.get("skew_value")
    skew_label = v.get("skew_label", "N/A")
    rsp_vs_spy = b.get("rsp_vs_spy", 0) or 0
    sectors_pos = b.get("sectors_positive", 0)
    sectors_tot = b.get("sectors_total", 11)

    # Opening read
    if vix is None:
        read = "No vol data — assume the worst case until it's back."
    elif vix < 13 and flow_score >= 70:
        read = f"VIX {vix:.1f} and flow is euphoric — this is where complacency bites. Size down, not up."
    elif vix < 15:
        read = f"VIX {vix:.1f} ({vix_label}) — calm tape. Good for swing work, but don't mistake quiet for safe."
    elif vix < 20:
        read = f"VIX {vix:.1f} — normal operating range. Standard size, standard stops."
    elif vix < 28:
        read = f"VIX {vix:.1f} — elevated. Widen stops or cut size in half, pick one."
    else:
        read = f"VIX {vix:.1f} — panic zone. Either stand aside or hunt for capitulation bounces only."

    points = []

    # VIX9D + SKEW as a group — short-term vs. tail risk profile
    if vix9d_ratio is not None and skew_value is not None:
        if vix9d_label == "Fear Spike" and skew_label in ("Elevated", "Extreme Tail Risk"):
            points.append({"icon": "🔴", "text": (
                f"VIX9D/VIX {vix9d_ratio:.2f}x ({vix9d_label}) + SKEW {skew_value:.0f} ({skew_label}) — "
                "near-term fear AND tail hedging both elevated simultaneously. "
                "This is a dual-layer risk-off signal. Cut size aggressively."
            )})
        elif vix9d_label == "Fear Spike":
            points.append({"icon": "⚠️", "text": (
                f"VIX9D/VIX {vix9d_ratio:.2f}x — near-term fear elevated above baseline. "
                "SKEW is calm ({skew_label}), so tail risk isn't the worry — it's the next few sessions. "
                "Reduce intraweek exposure."
            )})
        elif skew_label in ("Elevated", "Extreme Tail Risk"):
            points.append({"icon": "⚠️", "text": (
                f"SKEW {skew_value:.0f} ({skew_label}) while near-term vol is calm (VIX9D {vix9d_label}) — "
                "smart money is quietly hedging tail risk while the tape looks fine. "
                "Carry protection or reduce gross exposure."
            )})
        elif vix9d_label == "Calm" and skew_label == "Complacent":
            points.append({"icon": "⚠️", "text": (
                f"VIX9D calm + SKEW {skew_value:.0f} (complacent) — no hedging demand anywhere. "
                "This is peak complacency territory; cheap protection worth considering."
            )})
        else:
            points.append({"icon": "✅", "text": (
                f"VIX9D {vix9d_label} · SKEW {skew_value:.0f} ({skew_label}) — "
                "risk profile normal across both near-term and tail dimensions."
            )})
    elif vix9d_ratio is not None:
        if vix9d_label == "Fear Spike":
            points.append({"icon": "⚠️", "text": f"VIX9D/VIX {vix9d_ratio:.2f}x — near-term fear elevated. Reduce intraweek exposure."})
        elif vix9d_label == "Calm":
            points.append({"icon": "✅", "text": f"VIX9D/VIX {vix9d_ratio:.2f}x — near-term calm, event risk low."})

    # VIX percentile
    if vix_pctile is not None:
        if vix_pctile <= 20:
            points.append({"icon": "⚠️", "text": f"VIX at {vix_pctile}th %ile of the year — historically cheap to hedge here."})
        elif vix_pctile >= 80:
            points.append({"icon": "✅", "text": f"VIX at {vix_pctile}th %ile — stress well-priced, contrarian long window often opens here."})

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

    # Breadth divergence
    if rsp_vs_spy < -0.4:
        points.append({"icon": "⚠️", "text": f"RSP lagging SPY by {abs(rsp_vs_spy):.2f}% — mega-caps masking weakness underneath."})
    elif sectors_pos <= 4:
        points.append({"icon": "🔴", "text": f"Only {sectors_pos}/{sectors_tot} sectors positive — breadth rolling, don't trust the index."})

    # Closing verdict
    if vix and vix < 15 and flow_score >= 75:
        verdict = "Complacency risk is my concern. Hedge cheap — it won't stay cheap."
    elif vix9d_label == "Fear Spike" and skew_label in ("Elevated", "Extreme Tail Risk"):
        verdict = "Dual vol warning active. Half size max until either VIX9D or SKEW normalises."
    elif vix and vix >= 25:
        verdict = "Volatility is in charge. Small size, tight stops, or nothing."
    elif score >= 65:
        verdict = "Green light. Standard risk budget applies."
    else:
        verdict = "Amber light. Half-size everything until signals clear."

    return {
        "persona": "The Risk Manager",
        "role": "VIX · VIX9D · SKEW · Flow · Drawdown",
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

    # RS-ranked sector list from the scoring engine — the real rotation signal
    sector_rs = m.get("sector_rs", []) or []
    rs_leaders  = [s for s in sector_rs[:3]  if s.get("rs_score", 0) > 0]
    rs_laggards = [s for s in sector_rs[-3:] if s.get("rs_score", 0) < 0]

    # Opening read — RS rotation narrative
    if rs_leaders and sector_rs:
        top_name = rs_leaders[0].get("name", "—")
        top_rs   = rs_leaders[0].get("rs_score", 0)
        if participation == "Broad" and growth >= 2:
            read = (f"Broad participation + growth leading. {top_name} is the RS leader ({top_rs:+.1f}). "
                    "This is the kind of tape that makes winners out of mediocre entries.")
        elif participation == "Narrow":
            read = (f"Narrow tape — {n_pos}/{n_tot} sectors positive. "
                    f"RS is concentrating in {top_name} ({top_rs:+.1f}). "
                    "Index is up because a handful of names are doing the work — don't confuse that with a healthy tape.")
        elif iwm_vs_spy > 0.4:
            read = (f"Small caps leading mega-caps by {iwm_vs_spy:+.2f}% with {top_name} topping the RS table — "
                    "textbook risk-on rotation, reach out the risk curve.")
        else:
            read = (f"Rotation is active. RS leaders: {', '.join(s['name'] for s in rs_leaders[:2])}. "
                    f"RS laggards: {', '.join(s['name'] for s in rs_laggards[:2]) if rs_laggards else '—'}. "
                    "Follow the RS rankings, not the headlines.")
    elif participation == "Narrow":
        read = f"Narrow tape — {n_pos}/{n_tot} sectors holding. Index strength masks underlying weakness."
    else:
        read = (f"Rotation is active — leader {leader.get('name', '—')} "
                f"({leader.get('change_pct', 0):+.2f}%), laggard {laggard.get('name', '—')} "
                f"({laggard.get('change_pct', 0):+.2f}%). Follow the money.")

    points = []

    # RS-ranked hunt list — sharper than simple day-change sort
    if rs_leaders:
        hunt_str = " · ".join(
            f"{s['name']} (RS {s['rs_score']:+.1f})" for s in rs_leaders
        )
        points.append({"icon": "🎯", "text": f"RS LEADERS — hunt here: {hunt_str}"})

    if rs_laggards:
        avoid_str = " · ".join(
            f"{s['name']} (RS {s['rs_score']:+.1f})" for s in rs_laggards
        )
        points.append({"icon": "⛔", "text": f"RS LAGGARDS — avoid or short: {avoid_str}"})

    # Equal-weight signal
    if rsp_vs_spy > 0.3:
        points.append({"icon": "✅", "text": f"RSP outperforming SPY by {rsp_vs_spy:+.2f}% — broad rotation, average stock is working."})
    elif rsp_vs_spy < -0.3:
        points.append({"icon": "⚠️", "text": f"RSP lagging SPY by {abs(rsp_vs_spy):.2f}% — top-heavy rally, only mega-caps working."})

    # Small caps
    if iwm_vs_spy > 0.4:
        points.append({"icon": "✅", "text": f"IWM leading by {iwm_vs_spy:+.2f}% — speculative appetite back, reach further out the risk curve."})
    elif iwm_vs_spy < -0.4:
        points.append({"icon": "⚠️", "text": f"IWM lagging by {abs(iwm_vs_spy):.2f}% — defensive rotation, risk-off under the surface."})

    # Closing verdict — keyed to RS leader
    top_leader_name = rs_leaders[0]["name"] if rs_leaders else leader.get("name", "—")
    if participation == "Broad" and growth >= 2:
        verdict = f"Rotate into RS leaders ({top_leader_name}). Follow, don't predict."
    elif participation == "Narrow":
        verdict = "Stay out of laggards. Only trade confirmed RS leaders with volume."
    else:
        verdict = f"RS leader is {top_leader_name} — that's your shopping list."

    return {
        "persona": "The Sector Rotator",
        "role": "RS Rotation · Leaders · Laggards",
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

    stances = [p["stance"] for p in others]
    bulls = stances.count("Bullish")
    bears = sum(1 for s in stances if s in ("Bearish", "Defensive"))
    cautious = stances.count("Cautious")

    # Read active conflicts directly from the scoring engine — this is the
    # key upgrade: Desk Head now synthesises real signal conflicts, not just
    # counts bull/bear votes from the other personas.
    all_conflicts = d.get("conflicts", [])
    warnings = [c for c in all_conflicts if c["severity"] == "warning"]
    n_warn = len(warnings)
    warn_names = " · ".join(c["title"] for c in warnings[:2])

    m = d["pillars"]["macro"]["details"]
    fomc_days = m.get("fomc_days")
    v = d["pillars"]["volatility"]["details"]
    vix = v.get("vix_level") or 20
    t = d["pillars"]["trend"]["details"]
    above_200 = t.get("above_200", False)

    # Opening read — stance vote + conflict awareness
    if bulls >= 3 and bears == 0 and n_warn == 0:
        read = f"Desk is aligned long. {bulls}/4 analysts bullish, zero bears. Conditions rarely get this clean — press size."
    elif bulls >= 3 and bears == 0 and n_warn > 0:
        read = f"Desk is aligned long but {n_warn} active conflict{'s' if n_warn > 1 else ''}: {warn_names}. Don't press size blindly — the warning signs are real."
    elif bears >= 3:
        read = f"Desk is aligned defensive. {bears}/4 analysts negative. Capital preservation trumps opportunity cost here."
    elif bulls >= 2 and bears <= 1 and n_warn > 0:
        read = f"Desk leans constructive ({bulls} bulls, {bears} defensive) but {n_warn} active conflict{'s' if n_warn > 1 else ''}: {warn_names}. Trade selectively — not every setup is equal right now."
    elif bulls >= 2 and bears <= 1:
        read = f"Desk leans constructive but not unanimous — {bulls} bulls, {cautious} cautious, {bears} defensive. Trade it, but don't force it."
    elif bulls == bears:
        read = "Split desk. That usually means chop. Smallest setups only, or sit on hands."
    else:
        read = f"Mixed picture — {bulls} bullish, {cautious} cautious, {bears} defensive. This is selectivity weather."

    points = []
    points.append({"icon": "🎯", "text": f"VERDICT: {decision} · Score {total}/100 · {pos_size}"})

    # Key event risk
    if fomc_days is not None and fomc_days <= 3:
        points.append({"icon": "🔴", "text": f"FOMC IN {fomc_days} DAYS — this overrides everything else. Cut size now."})
    elif vix >= 25:
        points.append({"icon": "⚠️", "text": "Elevated vol — realized and implied both up. Risk budget shrinks mechanically."})
    elif not above_200:
        points.append({"icon": "⚠️", "text": "SPY below 200d — bear-market rules apply. Quick in, quick out."})

    # Surface top-2 WARNING conflicts as direct action items.
    # Extract the actionable clause after the em-dash; trim to 100 chars.
    for c in warnings[:2]:
        parts = c["detail"].split(" — ", 1)
        action = parts[1] if len(parts) > 1 else c["detail"]
        if len(action) > 100:
            action = action[:97] + "…"
        points.append({"icon": "⚠️", "text": f"{c['title']}: {action}"})

    # Execution rule — base tier from score, automatically downgraded one
    # step if any WARNING conflicts are active.
    if fomc_days is not None and fomc_days <= 3:
        rule = "FLAT into FOMC. Any new positions must close before 2:00 ET on decision day."
    elif not above_200:
        rule = "STAND ASIDE. No new longs. Cash is a position — wait for conditions to clear."
    elif total >= 85 and vix < 20 and (fomc_days is None or fomc_days > 7):
        rule = ("STANDARD SIZE (conflicts active — downgraded from FULL). A+ setups only, not A/B."
                if warnings else
                "FULL SIZE. Press the bid on A/B setups. Add on intraday pullbacks to 20d.")
    elif total >= 70:
        rule = ("HALF SIZE (conflicts active — downgraded from STANDARD). Tighter stops than normal."
                if warnings else
                "STANDARD SIZE. Run your normal game. A/B+ setups, stops below the entry base.")
    elif total >= 55:
        rule = ("MINIMAL (conflicts active — downgraded from HALF). One position max, tightest stops."
                if warnings else
                "HALF SIZE. A+ setups only. Clean pullback entries, stops at the breakout level.")
    elif total >= 40:
        rule = ("STAND ASIDE — too many conflicts at this score level."
                if warnings else
                "MINIMAL. Quarter size max. Tightest stops, take profits at first resistance.")
    else:
        rule = "STAND ASIDE. No new longs. Cash is a position — wait for conditions to clear."

    points.append({"icon": "⚡", "text": f"EXECUTION: {rule}"})

    # Final verdict — conflict-aware
    if n_warn >= 2 and total >= 55:
        verdict = f"{n_warn} active conflicts — size down one tier, trust A+ setups only."
    elif n_warn >= 1 and total >= 70:
        verdict = "Good tape with active conflicts — run your process, respect the warnings."
    elif total >= 85:
        verdict = "Strong tape. Don't overthink it — press size."
    elif total >= 70:
        verdict = "Good tape. Run your process, don't force it."
    elif total >= 55:
        verdict = "Be patient. One A+ trade beats five B trades."
    elif total >= 40:
        verdict = "Skeptical participation only. Protect your capital."
    else:
        verdict = "Cash is a position. Sit on hands."

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
