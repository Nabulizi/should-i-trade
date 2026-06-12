# Live Vol-Target Exposure Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the evidence-backed vol-target exposure number (the no-pillar dial that beat the score in backtest) as a companion line in the dashboard hero.

**Architecture:** A pinned constant `VOL_TARGET_K` in `config.py` (derived offline from the backtest's own bisection), one pure function in `scoring.py` computing `clamp(k / realized 20d vol, 0..100%)` from the SPY closes already fetched per refresh, a new optional payload field, and a pure HTML-string renderer exported from `app.js` (matching the repo's testable-pure-function pattern). Null payload → hidden line.

**Tech Stack:** Python 3.10+ stdlib; vanilla JS + Vitest.

**Spec:** `docs/superpowers/specs/2026-06-12-vol-target-display-design.md`
**Branch:** `feat/vol-target-display` (already checked out; spec committed).

**The derived constant (already computed — provenance below):**

```
selective exposure target = 62.60%   (full-sample Score>=55 rule, 2005-2026)
k = 0.489724                          (percent daily-return vol units)
achieved avg exposure = 62.60%
```

Derivation command (re-runnable; requires `backtest_results.csv` from the replay):

```bash
python3 - <<'EOF'
import backtest_report, backtest_stats
rows = backtest_report.load_rows("backtest_results.csv")
selective = backtest_report.strategy(rows, "sel", lambda r: r["total"] >= 55)
target = selective["exposure_pct"] / 100.0
vols = backtest_stats.realized_vol_series(rows)
def exposures_for(k):
    return [target if v is None or v <= 0 else min(1.0, k / v) for v in vols]
def avg_block(k):
    e = exposures_for(k)
    return backtest_stats._mean([e[i] for i in range(0, len(rows), backtest_stats.BLOCK_DAYS)])
lo, hi = 0.0, 1000.0
for _ in range(80):
    mid = (lo + hi) / 2
    if avg_block(mid) < target: lo = mid
    else: hi = mid
print(f"k = {(lo + hi) / 2:.6f}")
EOF
```

**Unit trap (enforced by tests):** the backtest's vol is the stdev of *percent* daily returns (1.2 means 1.2%). The live computation must build percent returns (`(c[i]/c[i-1] - 1) * 100`) before the stdev, or the exposure is silently ~100x off.

---

### Task 1: Backend — constant, model, pure function, payload wiring

**Files:**
- Modify: `config.py`
- Modify: `models.py` (near `_DashboardResultRequired`, ~line 188)
- Modify: `scoring.py` (config import; new function near `_day_streak`; `compute_dashboard` return dict)
- Modify: `test_scoring.py`

- [ ] **Step 1: Write the failing test**

Append to `test_scoring.py` (above the runner block), following the file's `ok()` convention:

```python
def test_vol_target_exposure() -> None:
    """Evidence-backed vol-target dial: clamp(k / realized vol, 0..100%)."""
    print("\nVol-target exposure dial:")
    import statistics

    # 21 closes producing exactly alternating +1% / -1% daily returns.
    closes = [100.0]
    for i in range(20):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    rets = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(1, 21)]
    expected_vol = statistics.stdev(rets)
    out = scoring.vol_target_exposure(closes)
    ok("returns dict for 21 closes", out is not None)
    expected_exp = min(100.0, max(0.0, 100.0 * scoring.VOL_TARGET_K / expected_vol))
    ok("exposure matches hand computation",
       abs(out["exposure_pct"] - round(expected_exp, 1)) < 1e-9)
    ok("realized vol matches hand computation",
       abs(out["realized_vol_pct"] - round(expected_vol, 1)) < 1e-9)

    # Calm-but-nonzero vol clamps at 100%.
    calm = [100.0]
    for i in range(20):
        calm.append(calm[-1] * (1.0003 if i % 2 == 0 else 0.9999))
    calm_out = scoring.vol_target_exposure(calm)
    ok("calm tape clamps at 100%", calm_out is not None and calm_out["exposure_pct"] == 100.0)

    ok("insufficient history -> None", scoring.vol_target_exposure([100.0] * 20) is None)
    ok("zero vol (constant closes) -> None", scoring.vol_target_exposure([100.0] * 21) is None)
    ok("empty input -> None", scoring.vol_target_exposure([]) is None)
```

Wire it into the runner block, after the `test_claim_hygiene()` call:

```python
    test_vol_target_exposure()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 test_scoring.py 2>&1 | tail -3`
Expected: AttributeError (`scoring` has no attribute `vol_target_exposure`), exit non-zero.

- [ ] **Step 3: Add the constants to `config.py`**

Append (near the other scoring tunables):

```python
# Vol-target exposure dial (see docs/backtest-report.md, Strategy Comparison:
# the no-pillar baseline that beat the Score>=55 rule on return, Sharpe, and
# max drawdown). VOL_TARGET_K derived 2026-06-12 by re-running the full-sample
# bisection from backtest_stats.calibrate_vol_exposures against
# backtest_results.csv (2005-2026, matched to the rule's 62.6% average
# exposure). Units: PERCENT daily-return volatility (1.2 means 1.2%).
# Derivation snippet: docs/superpowers/plans/2026-06-12-vol-target-display.md
VOL_TARGET_K = 0.489724
VOL_TARGET_WINDOW = 20   # trading days of realized vol
```

- [ ] **Step 4: Add `VolTargetInfo` to `models.py`**

Above `_DashboardResultRequired` add:

```python
class VolTargetInfo(TypedDict):
    """Evidence-backed vol-target exposure dial (see docs/backtest-report.md)."""

    exposure_pct: float
    realized_vol_pct: float
```

Inside `_DashboardResultRequired`, after `spy_streak: SpyStreak`, add:

```python
    vol_target: VolTargetInfo | None
```

- [ ] **Step 5: Implement in `scoring.py`**

a) Find scoring's existing `from config import (...)` (or `import config`) statement and add `VOL_TARGET_K` and `VOL_TARGET_WINDOW` to it, following its existing style. Add `VolTargetInfo` to the existing `from models import (...)` statement the same way.

b) Add near `_day_streak`:

```python
def vol_target_exposure(closes: list[float]) -> VolTargetInfo | None:
    """Evidence-backed exposure dial: clamp(VOL_TARGET_K / realized vol, 0..100%).

    closes: chronological adjusted closes (most recent last); needs at least
    VOL_TARGET_WINDOW + 1 points. Returns None when history is insufficient,
    contains non-positive prices, or volatility is zero. Vol units match the
    backtest calibration: PERCENT daily returns (see config.VOL_TARGET_K).
    """
    if not closes or len(closes) < VOL_TARGET_WINDOW + 1:
        return None
    tail = closes[-(VOL_TARGET_WINDOW + 1):]
    if any(c is None or c <= 0 for c in tail):
        return None
    rets = [(tail[i] / tail[i - 1] - 1) * 100 for i in range(1, len(tail))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol = var ** 0.5
    if vol <= 0:
        return None
    exposure = min(100.0, max(0.0, 100.0 * VOL_TARGET_K / vol))
    return {"exposure_pct": round(exposure, 1), "realized_vol_pct": round(vol, 1)}
```

c) In `compute_dashboard`'s returned dict, after `"spy_streak":        spy_streak,` add:

```python
        "vol_target":        vol_target_exposure(spy_closes_spliced),
```

(`spy_closes_spliced` is already computed a few lines above for the streak.)

- [ ] **Step 6: Run tests**

Run: `python3 test_scoring.py 2>&1 | tail -2 && python3 test_contracts.py 2>&1 | tail -1`
Expected: scoring ALL PASS (182/182). Contracts: the keys-parity test (`test_keys_match_dashboard_result_typeddict`) must still pass because BOTH the TypedDict and the payload gained the key together — if it fails, the wiring and the model are out of sync; STOP and report.

- [ ] **Step 7: Commit**

```bash
git add config.py models.py scoring.py test_scoring.py
git commit -m "feat: compute evidence-backed vol-target exposure in the dashboard payload"
```

---

### Task 2: Contract test for the new payload field

**Files:**
- Modify: `test_contracts.py` (inside `class TestDashboardContracts`)

- [ ] **Step 1: Add the test**

```python
    def test_vol_target_is_none_or_well_formed(self):
        self.assertIn("vol_target", self.payload)
        vt = self.payload["vol_target"]
        if vt is not None:
            self.assertIsInstance(vt["exposure_pct"], float)
            self.assertIsInstance(vt["realized_vol_pct"], float)
            self.assertGreaterEqual(vt["exposure_pct"], 0.0)
            self.assertLessEqual(vt["exposure_pct"], 100.0)
            self.assertGreater(vt["realized_vol_pct"], 0.0)
```

- [ ] **Step 2: Run**

Run: `python3 test_contracts.py 2>&1 | tail -1`
Expected: OK (18 tests). The fixture payload may legitimately produce `None` (short fixture history) — the test asserts the key either way.

- [ ] **Step 3: Commit**

```bash
git add test_contracts.py
git commit -m "test: contract for the vol_target payload field"
```

---

### Task 3: Frontend — pure renderer, hero wiring, JS tests

**Files:**
- Modify: `static/app.js`
- Modify: `static/app.test.js`

- [ ] **Step 1: Write the failing JS tests**

In `static/app.test.js`, add `volTargetLine` to the import list from `./app.js`, then append:

```javascript
// ── volTargetLine ─────────────────────────────────────────────────────────
describe('volTargetLine', () => {
  it('renders the rounded exposure percentage and the evidence label', () => {
    const html = volTargetLine({ exposure_pct: 72.4, realized_vol_pct: 0.7 });
    expect(html).toContain('~72% exposure');
    expect(html).toContain('vol-target-line');
    expect(html).toContain('beat the score');
  });

  it('returns an empty string for null, undefined, or malformed input', () => {
    expect(volTargetLine(null)).toBe('');
    expect(volTargetLine(undefined)).toBe('');
    expect(volTargetLine({})).toBe('');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test 2>&1 | tail -5`
Expected: FAIL — `volTargetLine` is not exported.

- [ ] **Step 3: Implement in `static/app.js`**

a) Add the pure renderer next to the other exported pure helpers (e.g. near `decisionForScore`):

```javascript
export function volTargetLine(volTarget) {
  if (!volTarget || typeof volTarget.exposure_pct !== 'number') return '';
  return `<div class="dc-row" id="vol-target-line"><span class="dc-label">Vol-target</span>` +
    `<span>~${Math.round(volTarget.exposure_pct)}% exposure — no-pillar baseline that beat the score in the 2005–2026 backtest</span></div>`;
}
```

b) In the decision-context template (the `ctx.innerHTML = \`` block, ~line 218), add one line after the posture div:

```javascript
    <div class="dc-posture">${posture}</div>
    ${volTargetLine(d.vol_target)}
```

(Hide-on-null falls out naturally: the function returns `''`.)

- [ ] **Step 4: Run JS tests and lint**

Run: `npm test 2>&1 | tail -3 && npm run lint 2>&1 | tail -2`
Expected: all tests pass (27), lint clean.

- [ ] **Step 5: Run the claim-hygiene guard (app.js is a hygiene surface)**

Run: `python3 test_scoring.py 2>&1 | tail -1`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add static/app.js static/app.test.js
git commit -m "feat: render vol-target exposure line in the dashboard hero"
```

---

### Task 4: Final verification

- [ ] **Step 1: Full battery**

Run: `python3 -m unittest discover 2>&1 | tail -2 && python3 test_scoring.py 2>&1 | tail -1 && npm test 2>&1 | tail -3 && npm run lint 2>&1 | tail -2 && python3 -m mypy models.py scoring.py backtest_report.py backtest_stats.py --ignore-missing-imports --no-error-summary && echo "mypy clean"`
Expected: OK / ALL PASS / JS pass / lint clean / mypy clean. (Note: if mypy was not previously run on scoring.py and reports pre-existing errors unrelated to this change, run it on `models.py backtest_report.py backtest_stats.py` only — the CI configuration — and report the scoring.py situation rather than fixing unrelated code.)

- [ ] **Step 2: Scope check**

Run: `git diff origin/feat/repositioning-copy-pass --stat`
Expected files only: `config.py`, `models.py`, `scoring.py`, `static/app.js`, `static/app.test.js`, `test_contracts.py`, `test_scoring.py`, plus the spec/plan under `docs/superpowers/`.

- [ ] **Step 3: Manual smoke**

Run `python3 server.py`, open http://localhost:8765, confirm the hero shows the "Vol-target ~NN% exposure" line under the posture text with live data (or is absent if SPY history fails), then stop the server.

- [ ] **Step 4: Use superpowers:finishing-a-development-branch**
