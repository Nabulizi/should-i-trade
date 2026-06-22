# Repositioning Copy Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite every copy surface that still claims a timing/drawdown edge the backtest report falsified, guarded by a permanent claim-hygiene test.

**Architecture:** Pure copy edits across six files (backend band strings, frontend fallback strings, HTML legend, README, methodology doc, CLAUDE.md) — no behavior, payload, or threshold changes. A claim-hygiene test in `test_scoring.py` (the repo's custom `ok()` style) permanently bans the falsified phrases from all copy surfaces, including the frontend files.

**Tech Stack:** Python stdlib, vanilla JS, markdown. Tests: `python3 test_scoring.py` (custom runner), `npm test`, `npm run lint`.

**Spec:** `docs/superpowers/specs/2026-06-12-repositioning-copy-pass-design.md`
**Branch:** `feat/repositioning-copy-pass` (stacked on `feat/backtest-robustness-analytics`; already checked out, spec committed).

**TDD note:** Task 1 writes the hygiene test and confirms it fails (red). It stays UNCOMMITTED until Task 5, after Tasks 2–4 have fixed every surface, then is committed green. Do not commit a failing test.

---

### Task 1: Write the failing claim-hygiene test

**Files:**
- Modify: `test_scoring.py` (do NOT commit in this task)

- [ ] **Step 1: Add the test function**

`test_scoring.py` uses a custom pattern: top-level `test_*()` functions calling `ok(label, cond)`, invoked from a runner list near the bottom (the last call is `test_day_streak()` just before the `total = _PASS + _FAIL` summary block). Add this function above the runner block:

```python
def test_claim_hygiene() -> None:
    """Bans performance claims that docs/backtest-report.md falsified."""
    print("\nClaim hygiene:")
    banned = [
        "low-drawdown regime",
        "drawdown timer",
        "drawdown/exposure timer",
        "drawdown risk elevated",
        "validated engagement line",
        "STRONG YES",
    ]
    root = os.path.dirname(os.path.abspath(__file__))
    surfaces = [
        "scoring.py",
        "README.md",
        os.path.join("docs", "backtest-methodology.md"),
        "CLAUDE.md",
        os.path.join("static", "app.js"),
        "should-i-trade-v6.html",
    ]
    for rel in surfaces:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            text = f.read()
        for phrase in banned:
            ok(f"{rel}: no {phrase!r}", phrase not in text)
    for band in scoring.DECISION_BANDS:
        ok(f"{band['decision']} action non-empty", bool(band["action"]))
        ok(f"{band['decision']} action fits badge (<90 chars)",
           len(band["action"]) < 90)
```

(Surfaces extend the spec's four files with `static/app.js` and `should-i-trade-v6.html` so the frontend copies are guarded too — both currently contain banned phrases, which is the point.)

- [ ] **Step 2: Wire it into the runner**

In the runner block, immediately after the `test_day_streak()` call, add:

```python
    test_claim_hygiene()
```

- [ ] **Step 3: Run and confirm it fails**

Run: `python3 test_scoring.py; echo "exit=$?"`
Expected: `exit=1`, with ✗ lines for at least: `scoring.py: no 'low-drawdown regime'`, `scoring.py: no 'drawdown/exposure timer'`, `scoring.py: no 'drawdown risk elevated'`, `README.md: no 'drawdown timer'`, `README.md: no 'drawdown/exposure timer'`, `README.md: no 'validated engagement line'`, `docs/backtest-methodology.md: no 'drawdown/exposure timer'`, `CLAUDE.md: no 'STRONG YES'`, `static/app.js: no 'low-drawdown regime'`, `static/app.js: no 'drawdown risk elevated'`.

**Do NOT commit.** Leave `test_scoring.py` modified in the working tree.

---

### Task 2: Backend + frontend band strings and HTML legend

**Files:**
- Modify: `scoring.py:66-81`
- Modify: `static/app.js:203-207`
- Modify: `should-i-trade-v6.html:155`

- [ ] **Step 1: Replace the `scoring.py` comment and action strings**

Replace this block:

```python
# De-risk gauge: a 2005-2026 walk-forward backtest showed the composite is a
# drawdown/exposure timer, not a forward-return predictor. Labels describe how
# much market risk the current regime is worth; the "engage" line is 55, not 70.
DECISION_BANDS = [
    {"min": 85, "decision": "RISK-ON",      "color": "green",  "position": "FULL EXPOSURE",
     "action": "Full exposure — low-drawdown regime, press the bid on A/B setups"},
    {"min": 70, "decision": "CONSTRUCTIVE", "color": "green",  "position": "STANDARD EXPOSURE",
     "action": "Standard exposure — constructive regime, run your normal game"},
    {"min": 55, "decision": "SELECTIVE",    "color": "yellow", "position": "MODERATE EXPOSURE",
     "action": "Moderate exposure — engage selectively, A+ setups, tight stops"},
    {"min": 40, "decision": "DE-RISK",      "color": "orange", "position": "REDUCED EXPOSURE",
     "action": "Reduced exposure — de-risk, very selective or sit out"},
    {"min": 0,  "decision": "RISK-OFF",     "color": "red",    "position": "DEFENSIVE / FLAT",
     "action": "Defensive — drawdown risk elevated, no new longs"},
]
```

with:

```python
# Market-conditions gauge: the 2005-2026 replay (docs/backtest-report.md) shows
# the composite describes the current regime but has no demonstrated timing
# edge over same-exposure baselines. Labels describe conditions and a suggested
# exposure posture; they are not validated trade signals. 55/70/85 are
# descriptive bands, not proven thresholds.
DECISION_BANDS = [
    {"min": 85, "decision": "RISK-ON",      "color": "green",  "position": "FULL EXPOSURE",
     "action": "Full exposure — calm, trending tape, press the bid on A/B setups"},
    {"min": 70, "decision": "CONSTRUCTIVE", "color": "green",  "position": "STANDARD EXPOSURE",
     "action": "Standard exposure — constructive tape, run your normal game"},
    {"min": 55, "decision": "SELECTIVE",    "color": "yellow", "position": "MODERATE EXPOSURE",
     "action": "Moderate exposure — mixed tape, engage selectively, A+ setups, tight stops"},
    {"min": 40, "decision": "DE-RISK",      "color": "orange", "position": "REDUCED EXPOSURE",
     "action": "Reduced exposure — choppy tape, very selective or sit out"},
    {"min": 0,  "decision": "RISK-OFF",     "color": "red",    "position": "DEFENSIVE / FLAT",
     "action": "Defensive — stressed tape, protect capital, no new longs"},
]
```

- [ ] **Step 2: Byte-match the `static/app.js` fallback ternary**

Replace:

```javascript
                : s >= 85 ? 'Full exposure — low-drawdown regime, press the bid on A/B setups'
                : s >= 70 ? 'Standard exposure — constructive regime, run your normal game'
                : s >= 55 ? 'Moderate exposure — engage selectively, A+ setups, tight stops'
                : s >= 40 ? 'Reduced exposure — de-risk, very selective or sit out'
                :           'Defensive — drawdown risk elevated, no new longs');
```

with:

```javascript
                : s >= 85 ? 'Full exposure — calm, trending tape, press the bid on A/B setups'
                : s >= 70 ? 'Standard exposure — constructive tape, run your normal game'
                : s >= 55 ? 'Moderate exposure — mixed tape, engage selectively, A+ setups, tight stops'
                : s >= 40 ? 'Reduced exposure — choppy tape, very selective or sit out'
                :           'Defensive — stressed tape, protect capital, no new longs');
```

- [ ] **Step 3: Fix the HTML legend**

In `should-i-trade-v6.html`, replace:

```html
          <span style="color:var(--green);">●</span> 70+: RISK-ON (full / standard exposure)<br>
```

with:

```html
          <span style="color:var(--green);">●</span> 85+: RISK-ON (full exposure)<br>
          <span style="color:var(--green);">●</span> 70–84: CONSTRUCTIVE (standard exposure)<br>
```

(The 55–69 / 40–54 / <40 lines below it are already accurate; leave them.)

- [ ] **Step 4: Verify**

Run: `python3 test_scoring.py 2>&1 | grep -c "✗"; npm test 2>&1 | tail -3; npm run lint 2>&1 | tail -2`
Expected: the ✗ count DROPS (scoring.py/app.js/html lines now pass; README/methodology/CLAUDE.md still fail — that's Tasks 3–4); `npm test` passes; lint clean. Also run `python3 -c "import scoring" 2>/dev/null || python3 -m py_compile scoring.py` to confirm syntax.

- [ ] **Step 5: Commit (copy files only — NOT test_scoring.py)**

```bash
git add scoring.py static/app.js should-i-trade-v6.html
git commit -m "copy: band actions and legend describe conditions, not outcomes"
```

---

### Task 3: README rewrite

**Files:**
- Modify: `README.md` (5 sites)

- [ ] **Step 1: Intro tagline (line ~5)**

Replace:

```markdown
A single-page, self-hosted **risk / de-risk gauge** for the session: it reads the market regime and tells you **how much market exposure the current environment is worth.**
```

with:

```markdown
A single-page, self-hosted **market-conditions gauge** for the session: it reads the market regime and turns current conditions into a suggested exposure posture.
```

- [ ] **Step 2: "What the score is (and isn't)" blockquote (line ~11)**

Replace:

```markdown
> **What the score is (and isn't).** A 2005–2026 walk-forward backtest showed the composite Market Quality Score is a **drawdown/exposure timer, not a forward-return predictor.** In the 2016+ validation window, a "long SPY when score ≥55, otherwise flat" rule cut max drawdown from ~−32% to ~−14% with ~69% exposure, but it lagged buy-and-hold on total return and Sharpe. It does **not** predict which days will be profitable — read it as a risk dial, not a green light. The engage line is **55**, not 70.
```

with:

```markdown
> **What the score is (and isn't).** The composite Market Quality Score describes market conditions; it is **not a timing signal**. In the 2005–2026 backtest, a no-pillar volatility-targeting baseline holding the same average exposure beat the "long SPY when score ≥ 55" rule on total return, Sharpe, and max drawdown (validation window: 1.06 vs 0.86 Sharpe, −11.1% vs −14.3% max drawdown). The rule beat its fair benchmark in 6 of 22 years, and forward-return correlations are negative. Read the dashboard as a conditions report and exposure prompt — see the [Backtest Report](docs/backtest-report.md) for the full evidence.
```

- [ ] **Step 3: First-Run Orientation bullet (line ~72)**

Replace:

```markdown
- Read the score as an exposure dial: **55** is the validated engagement line, **70** is constructive, and **85** is the strongest risk-on band.
```

with:

```markdown
- Read the score as a conditions/exposure dial: **55/70/85** mark descriptive bands (selective / constructive / strongest), not validated signal thresholds.
```

- [ ] **Step 4: Project tree + test commands**

After the line:
```markdown
├── backtest_report.py     # Offline Markdown report generator for backtest_results.csv
```
insert:
```markdown
├── backtest_stats.py      # Pure offline stats: baselines, bootstrap CIs, costs
```

After the line:
```markdown
├── test_backtest_report.py # Backtest report generator tests
```
insert:
```markdown
├── test_backtest_stats.py # Baseline/bootstrap/cost analytics tests
```

In the test-commands block, after:
```markdown
python3 test_backtest_report.py # offline generated-report contract tests
```
insert:
```markdown
python3 test_backtest_stats.py # baseline/bootstrap/cost analytics tests
```

- [ ] **Step 5: Correlation note (line ~165)**

Replace:

```markdown
> **Correlation note (22-year backtest):** Breadth↔Momentum share significant signal (r=0.70) and Vol↔Breadth correlate at r=0.71 — the composite has ~3 effective independent inputs, not 5. Macro is the only truly orthogonal pillar. The score still works as a drawdown timer; just don't interpret the 5 bars as 5 independent votes.
```

with:

```markdown
> **Correlation note:** the five pillars are substantially correlated — the composite behaves like roughly three effective inputs, not five independent votes. Macro is the most independent pillar. Don't read the five bars as five separate confirmations.
```

- [ ] **Step 6: Verify and commit**

Run: `python3 test_scoring.py 2>&1 | grep "✗" | grep README`
Expected: no output (all README hygiene lines now ✓).

```bash
git add README.md
git commit -m "copy: README leads with the vol-target evidence, drops falsified claims"
```

---

### Task 4: Methodology doc + CLAUDE.md

**Files:**
- Modify: `docs/backtest-methodology.md`
- Modify: `CLAUDE.md:73`

- [ ] **Step 1: Methodology intro + headline claim**

Replace:

```markdown
This document records how the Market Quality Score claims should be reproduced
and interpreted. The dashboard is a risk/exposure gauge, not a return predictor
or financial advice.

## Current Headline Claim

The README summarizes a 2005-2026 walk-forward replay showing that the
composite score is most useful as a drawdown/exposure timer:

- Higher scores did not reliably predict which individual days would be
  profitable.
- A rule that stayed long SPY when the score cleared the engagement threshold
  and de-risked when it did not materially reduced drawdown versus buy-and-hold,
  with lower exposure and lower absolute return in the documented validation
  window.
- The validated engagement threshold is 55, not 70.
```

with:

```markdown
This document records how the Market Quality Score claims should be reproduced
and interpreted. The dashboard is a market-conditions and exposure gauge, not a
return predictor or financial advice.

## Current Headline Claim

The README summarizes the composite score conservatively:

- Higher scores did not reliably predict which individual days would be
  profitable.
- A rule that stays long SPY when the score clears the engagement threshold must
  be judged against same-exposure SPY and no-pillar volatility baselines before
  it can claim timing value.
- A no-pillar volatility-targeting baseline at matched exposure outperformed
  the score-timing rule on return, Sharpe, and max drawdown in the validation
  window; treat any timing claim as unsupported until this baseline is beaten
  out of sample.
- Drawdown reduction is useful only after separating it from the mechanical
  benefit of simply holding less SPY.
- The current engagement threshold under test is 55, not 70.
```

- [ ] **Step 2: Methodology "Metrics To Check" list**

Replace:

```markdown
- Per-pillar information coefficient.
- Year-by-year behavior, especially weak market years.
```

with:

```markdown
- Per-pillar information coefficient.
- Strategy performance versus constant same-exposure SPY.
- Strategy performance versus a no-pillar volatility-targeting baseline.
- Year-by-year strategy returns, exposure, and drawdown, especially weak market
  years.
- Bootstrap confidence intervals for IC, decision-band means, decile means, and
  the decile 1 minus decile 10 spread.
- Cost/slippage sensitivity across realistic bps assumptions.
```

- [ ] **Step 3: CLAUDE.md thresholds line**

Replace:

```markdown
Decision thresholds: ≥85 STRONG YES → 70 YES → 55 CAUTION → 40 NO → <40 WAIT.
```

with:

```markdown
Decision bands: ≥85 RISK-ON → 70 CONSTRUCTIVE → 55 SELECTIVE → 40 DE-RISK → <40 RISK-OFF (descriptive bands, not validated thresholds).
```

- [ ] **Step 4: Verify and commit**

Run: `python3 test_scoring.py 2>&1 | tail -3`
Expected: `ALL PASS` (every hygiene line now ✓).

```bash
git add docs/backtest-methodology.md CLAUDE.md
git commit -m "copy: methodology and CLAUDE.md reflect baseline-gated claims"
```

---

### Task 5: Commit the now-green hygiene test + full verification

**Files:**
- Modify: `test_scoring.py` (commit the Task 1 change)

- [ ] **Step 1: Prove the test still guards (mutation check)**

Temporarily append `# low-drawdown regime` to the end of `scoring.py` and run `python3 test_scoring.py; echo "exit=$?"` — expected `exit=1` with one ✗. Then restore it with `git checkout -- scoring.py` (safe: scoring.py was committed clean in Task 2). Re-run, expect `ALL PASS`.

- [ ] **Step 2: Full verification battery**

Run: `python3 test_fixes.py && python3 test_scoring.py && python3 test_data.py && python3 test_contracts.py && python3 test_backtest_report.py && python3 test_backtest_stats.py && python3 test_analysis.py && python3 test_smoke.py`
Expected: all OK / ALL PASS.

Run: `npm test 2>&1 | tail -3 && npm run lint 2>&1 | tail -2`
Expected: tests pass, lint clean.

Run: `git diff feat/backtest-robustness-analytics --stat`
Expected: exactly these files: `scoring.py`, `static/app.js`, `should-i-trade-v6.html`, `README.md`, `docs/backtest-methodology.md`, `CLAUDE.md`, `test_scoring.py`, plus the spec and this plan under `docs/superpowers/`.

- [ ] **Step 3: Commit**

```bash
git add test_scoring.py
git commit -m "test: claim-hygiene guard bans falsified performance claims from copy surfaces"
```

- [ ] **Step 4: Manual smoke (optional but recommended)**

Run `python3 server.py`, open http://localhost:8765, confirm the badge/posture strings render and fit at default width, then stop the server.
