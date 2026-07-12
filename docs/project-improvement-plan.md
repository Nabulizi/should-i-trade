# Should I Trade? — Shared Improvement Plan

**Status:** Active shared source of truth  
**Plan version:** 1.0  
**Created:** 2026-07-11  
**Production baseline:** `main` at `87947d4`  
**Research branch at creation:** `feat/pit-v0-fundamental-backtest` at `95f5137`

This is the canonical implementation and research plan for the project. Codex,
Claude, and human contributors should read it before related work, refer to task
IDs in commits and pull requests, and update status when work is merged.

---

## Technical Summary

The project has a strong engineering and research foundation, but its product
language currently claims more decision authority than its evidence supports.
The historical replay shows that the five-pillar score describes market state but
does not provide demonstrated return-timing value over fair exposure-matched
baselines. The immediate objective is not to optimize or invert the score. It is
to make the product truthful, operationally reliable, and clear about what is
observed, inferred, and unvalidated.

The program has four stages:

1. **Correctness and operational safety:** fix confirmed bugs, dead contracts,
   resource leaks, documentation drift, and privacy/source issues.
2. **Evidence-aligned product:** remove unsupported trade directives, distinguish
   observation from computation time, make reliability independent of score, and
   present volatility sizing honestly.
3. **Isolated model research:** evaluate signal duplication, pillar saturation,
   normalization, and alternative structures without silently changing the score.
4. **Prospective self-grading:** persist timestamped, versioned forecasts and grade
   them against predeclared outcomes using live out-of-sample evidence.

The intended product identity is:

> A U.S. equity market-conditions and risk-budget dashboard that explains the
> current environment. It is not a standalone trade-entry or return-timing system.

---

## Evidence Baseline

The current report covers 5,375 trading days from 2005-01-03 through 2026-05-14.
Its validation window is 2016-01-04 through 2026-05-14.

| Evidence | Current result | Product implication |
|---|---:|---|
| Score ≥55 validation Sharpe | 0.85 | Does not establish timing value |
| Constant 70% SPY Sharpe | 0.95 | Simple matched exposure performed better |
| Matched vol-target Sharpe | 1.05 | Strongest tested risk-adjustment mechanism |
| Score ≥55 validation max drawdown | -14.3% | Better than constant exposure, worse than vol target |
| Matched vol-target max drawdown | -11.1% | Supports prominent, carefully labeled volatility context |
| Five-day score IC | -0.078 | Higher scores did not predict higher returns |
| Years score rule beat matched baseline | 6 of 22 | Timing value is not stable |
| Next-session range-efficiency hypothesis | Failed | High scores did not precede cleaner sessions |

Sources:

- [`backtest-report.md`](backtest-report.md)
- [`backtest-methodology.md`](backtest-methodology.md)
- [`../scoring.py`](../scoring.py)
- [`../backtest.py`](../backtest.py)

### What the evidence establishes

- The score is an interpretable description of trend, participation, volatility,
  and macro context.
- Low-score periods tend to have larger subsequent ranges and higher volatility.
- A simple volatility-control baseline produced better risk-adjusted results than
  the score-timing rule in the published comparison.
- The score should not issue directional trade authorization.

### What the evidence does not establish

- That users should invert the score and buy every RISK-OFF condition.
- That low-score days are profitably day-tradeable after execution costs.
- That the live intraday score behaves like the tested EOD score.
- That one default volatility target suits every user.
- That the five displayed pillars are independent confirmations.

---

## Accepted Decisions

These decisions are settled for the current program unless new evidence justifies
a documented change.

### D-001 — The score is context, not authorization

The composite may describe market conditions. It must not tell users to “press the
bid,” use full size, avoid all longs, or treat bands as a validated strategy.

### D-002 — Do not invert the failed score

Negative forward-return correlation does not validate a contrarian strategy. Any
inverse strategy requires its own executable, cost-aware, out-of-sample test.

### D-003 — Promote volatility context without personalizing it

The volatility dial should be prominent, but labeled as an illustrative
SPY-equivalent risk-budget calculation. `VOL_TARGET_K = 0.489724` corresponds to
approximately 7.8% annualized volatility (`0.489724% × sqrt(252)`). A future UI
may let users select a target, but must not imply portfolio suitability.

### D-004 — Confidence must be independent of direction

The current UI derives confidence from the score band. Reliability must instead
use freshness, coverage, signal agreement, boundary distance, and model stability.
Until implemented, remove the confidence display.

### D-005 — Separate horizons

The product will ultimately distinguish:

- **Session context:** premarket and intraday observations.
- **Swing context:** roughly 20–60 trading days.
- **Strategic context:** multi-month macro and credit conditions.

### D-006 — Numerical changes require versioned revalidation

Removing scored features, normalizing ranges, changing weights, or changing
thresholds is model research. It must occur on an isolated branch, create a model
version, rerun the replay, and regenerate the report before production adoption.

### D-007 — Return IC does not determine weights by itself

Do not increase Macro’s weight merely because it has positive return IC. Weights
may only be refit after the intended target is declared: return, drawdown,
volatility, range, trend persistence, or another measurable outcome.

### D-008 — Personas are lenses, not independent votes

Rule-based and Gemini personas read overlapping inputs. They must not manufacture
consensus or escalate size based on vote counts. AI may summarize supplied
evidence and uncertainty; it may not invent credentials or authoritative sizing.

### D-009 — Prospective evidence outranks retrospective tuning

After correctness and product-alignment work, the largest investment is a
versioned prospective log graded against predeclared outcomes.

---

## Scope and Non-Goals

### In scope

- Current Python/vanilla-JS dashboard and public Render demo.
- Score/persona contracts, presentation, provenance, and operational safety.
- Published replay methodology and prospective outcome tracking.
- Personal watchlist behavior and public-demo privacy.
- Repository documentation and release hygiene needed for collaboration.

### Not in scope for the first two phases

- Broker integration or automated execution.
- Personalized financial advice or portfolio optimization.
- A new predictive ML model.
- A contrarian strategy based only on negative IC.
- Extension of historical `quantconnect_*.py` scripts; new systematic research
  remains in `../quant-research`.
- A full compliance program unless the project becomes commercial or personalized.

---

## Workstream Overview

| Phase | Goal | Expected duration | Model output changes? |
|---|---|---:|:---:|
| P0 | Correctness, contracts, operations, documentation | 1–2 days | Minimal |
| P1 | Evidence-aligned product and hierarchy | Several days | Limited/versioned |
| P2 | Isolated scoring research and v7 candidate | 1–3 weeks | Yes, research only |
| P3 | Prospective logging and self-grading | 1–2 weeks MVP | No at first |
| P4 | Optional public-research hardening | As required | No |

Statuses: `pending`, `in_progress`, `blocked`, `done`, `deferred`.

---

## P0 — Correctness and Operational Safety

P0 should ship in small reviewable pull requests and avoid numerical score changes
unless explicitly stated.

### P0-A — Visible and dead label contracts

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P0-001 | done | Fix missing `f` prefix for `{skew_label}` | No literal placeholder; regression test covers branch |
| P0-002 | done | Define shared SKEW/VIX9D/MACD label constants or literals | Scoring and analysis use the same contract |
| P0-003 | done | Repair unreachable SKEW branches | Every compared label is producible or removed; reachability tested |
| P0-004 | done | Add producer-consumer label contract test | Test fails on unemittable labels |
| P0-005 | done | Audit other cross-module label contracts | Findings recorded; risky contracts centralized/tested |

Known affected files: `analysis.py`, `scoring.py`, `test_analysis.py`, and
`test_scoring.py`.

### P0-B — Remove unsupported action language everywhere

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P0-006 | done | Rewrite backend `DECISION_BANDS` actions as context | No press/full-size/entry/stop/directional instruction |
| P0-007 | done | Update duplicated frontend fallback actions | Backend and frontend agree semantically |
| P0-008 | done | Remove prescriptive sizing from rule-based personas | Prohibited phrases absent outside intentional historical quotes |
| P0-009 | done | Add claim-hygiene tests | CI blocks reintroduction of unsupported authority |

Recommended descriptive bands:

| Band | Meaning |
|---|---|
| RISK-ON | Calm, broad, established uptrend conditions |
| CONSTRUCTIVE | Positive trend with generally supportive participation |
| SELECTIVE | Mixed conditions or meaningful internal disagreement |
| DE-RISK | Weak/choppy conditions with elevated adverse-move risk |
| RISK-OFF | Stressed or structurally weak conditions; no timing implication |

### P0-C — Runtime resource risks

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P0-010 | done | Correct rate-limiter eviction | All buckets are pruned; empty buckets removed; bounded-memory test |
| P0-011 | done | Add configurable SSE client cap | Excess connections receive 503 without permanent thread allocation |
| P0-012 | done | Add SSE lifetime/idle policy | Dead/stuck clients are reclaimed and cleanup tested |
| P0-013 | done | Verify client IP behind Render/proxies | Deployment behavior documented and limiter uses trustworthy identity |
| P0-014 | done | Implement `HEAD` for root/health/static routes | Correct status/headers, empty body |

Do not hardcode an unexplained SSE cap. Configure it, test it, and observe metrics.

### P0-D — Environment and documentation drift

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P0-015 | done | Add `.nvmrc` and `.node-version` for Node 20 | Version managers select supported Node |
| P0-016 | done | Add `package.json` `engines` | Unsupported versions warn clearly |
| P0-017 | done | Support Node 26 or explicitly reject it | Tests pass or support boundary is unambiguous |
| P0-018 | done | Sync README health/metrics examples | Keys exactly match responses |
| P0-019 | done | Correct refresh-cadence documentation | 60s cache TTL and 5m client polling distinguished |
| P0-020 | done | Correct v5/v6 drift | Server, banner, README, and page agree |
| P0-021 | done | Add a license | Root license exists and README identifies it |

### P0-E — Provenance, watchlist quality, and privacy

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P0-022 | done | Split live quote and historical sources | Yahoo live levels are not labeled CBOE/Treasury |
| P0-023 | done | Gate watchlist classification on minimum history | Insufficient history becomes `No Data`, never “below MA” |
| P0-024 | done | Remove filesystem paths from API | No local/Render absolute paths in public payloads |
| P0-025 | done | Replace personal watchlist with generic example | Personal file is not shipped or served |
| P0-026 | done | Git-ignore personal watchlists while retaining examples | Accidental commit prevented; example remains tracked |

### P0 validation gate

```bash
python3 -m unittest discover
python3 test_fixes.py
python3 test_scoring.py
python3 test_data.py
python3 test_contracts.py
python3 test_analysis.py
python3 test_smoke.py
npm run lint
npm test
```

Also verify:

- `rg -n "press (the bid|size)|green light|FULL SIZE|\\{skew_label\\}" .`
- Rate-limiter bucket count drops after expiry in an automated test.
- SSE rejection and disconnect cleanup are tested.
- Public payload provenance is correct.

---

## P1 — Align the Product With the Evidence

P1 is a product-truth and behavioral-safety change, not merely a redesign.

### P1-A — Regime, reliability, and freshness

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P1-001 | done | Remove score-derived confidence bar | Score direction is never called confidence |
| P1-002 | done | Define reliability schema | Coverage, critical inputs, age, availability, agreement, boundary distance |
| P1-003 | done | Add per-source timestamps and ages | Quote/history/calculation times are distinguishable |
| P1-004 | done | Add closed-market framing | Weekend/holiday UI identifies represented session and planning-only state |
| P1-005 | done | Split `calculated_at` and `market_data_as_of` | Ambiguous timestamp removed via migration/versioning |
| P1-006 | done | Add next-session context | Header correctly states premarket/open/after-hours/weekend/holiday/closed |

Reliability is independent of direction. A low score can have high reliability.

### P1-B — Honest volatility-budget calculation

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P1-007 | done | Rename as illustrative SPY volatility budget | Copy includes target, realized vol, horizon, and “not personalized” |
| P1-008 | done | Express in annualized-volatility units | API/UI expose target and realized annual vol |
| P1-009 | done | Add optional user-selected target volatility | Bounded presets/input persist locally |
| P1-010 | done | Resolve posture-versus-vol contradiction | No unexplained “standard/full” beside a different percentage |
| P1-011 | done | Disclose formula and limitations | SPY-only, trailing window, no covariance/suitability are visible |

Reference formula:

```text
realized_annual_vol = std(daily_returns, 20d) × sqrt(252)
spy_equivalent_exposure = clamp(target_annual_vol / realized_annual_vol, 0, 1)
```

### P1-C — Simplify the first viewport

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P1-012 | done | Make regime band primary and integer secondary | Environment, reliability, and as-of precede details |
| P1-013 | done | Make evidence disclaimer prominent | States no demonstrated return-timing edge |
| P1-014 | done | Remove radar chart | Correlated pillars not presented as independent axes |
| P1-015 | done | Use evidence bars with uncertain/missing states | Contribution and availability are clear |
| P1-016 | done | Reduce semantic color overload | Color reserved for regime, warnings, and reliability failures |
| P1-017 | done | Rename emotional watchlist labels | “Broken/Avoid” replaced with neutral structural language |
| P1-018 | done | Make persona output concise by default | One-line lenses first; detail expands on demand |

### P1-D — Remove manufactured authority

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P1-019 | done | Explain personas as shared-input lenses | UI does not imply independent analysts |
| P1-020 | done | Remove vote-count sizing escalation | No action depends on N-of-4 consensus |
| P1-021 | done | Remove fictional Gemini credentials | No invented experience/employment/best-analyst claims |
| P1-022 | done | Remove AI size/entry/stop directives | Output bounded to evidence, disagreement, missing data, falsification |
| P1-023 | done | Validate AI values and lengths | Stances, point counts, text lengths, fields constrained |
| P1-024 | done | Make AI provenance visible | Model, time, shared-input limitation, fallback explicit |

### P1-E — Calendar overlays become context-only

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P1-025 | done | Remove FOMC point adjustment | Event remains visible context |
| P1-026 | done | Remove OpEx point adjustment | Event remains visible context |
| P1-027 | done | Remove seasonality point adjustment | Context-only or removed until validated |
| P1-028 | done | Version and validate numerical change | Band occupancy measured; replay/report updated if totals change |

The replay already neutralizes these overlays, but removing them live changes totals.
Treat this as a small model-version change.

### P1-F — Reduce noise-triggered behavior

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P1-029 | done | Make band-change-only push default | Small integer moves do not prompt action |
| P1-030 | done | Add configurable hysteresis/persistence | One-point boundary oscillation prevented and tested |
| P1-031 | done | Estimate meaningful change threshold | Derived from historical score variability |
| P1-032 | done | Separate informational alerts from action | Alerts state observation and uncertainty only |

### P1 acceptance scenario

On a Saturday, the first viewport should read approximately:

```text
MARKET CLOSED — WEEKEND
Based on Friday Jul 10 regular-session close · calculated Sat 23:22 ET

Environment: Constructive trend conditions
Reliability: High — 37/37 quotes, critical histories current
Illustrative SPY vol budget: 53% for an 8% annual-vol target

Conditions report only. No demonstrated return-timing edge.
```

It must not imply the Saturday calculation time is the market observation time.

---

## P2 — Isolated Model Research and v7 Candidate

P2 must not be mixed with maintenance. Preserve v6 as the comparison baseline.

### Research questions

1. What measurable outcome should the score describe or predict?
2. How much unique information does each feature add?
3. How often do pillars saturate, altering effective weights?
4. Are three orthogonal factors more stable and honest than five pillars?
5. Does any candidate improve usefulness without manufacturing fit?

### P2-A — Declare targets before fitting

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P2-001 | pending | Select one primary target per horizon | Written before experiments |
| P2-002 | pending | Define session/swing/strategic cohorts | Times, horizons, and permissible inputs explicit |
| P2-003 | pending | Freeze train/validation/lockbox dates | No decision uses lockbox outcomes |
| P2-004 | pending | Create experiment ledger | Every feature/weight/threshold attempt recorded |

Candidate targets: realized volatility, maximum adverse excursion, range size,
range efficiency, trend persistence, and forward drawdown probability. Return
prediction is optional and must be explicitly selected.

### P2-B — Measure effective weights

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P2-005 | pending | Enumerate theoretical min/max and reachable states | Tests document ranges; momentum ceiling/trend saturation addressed |
| P2-006 | pending | Measure empirical distributions | Occupancy, saturation, variance, and discrimination reported |
| P2-007 | pending | Calculate effective contributions | Nominal weight × empirical variation shown |
| P2-008 | pending | Run weight perturbation sensitivity | Band/outcome stability quantified |

### P2-C — Remove duplication and misleading proxies

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P2-009 | pending | Ablate TQQQ-SQQQ “Flow Sentiment” | Incremental value beyond index direction measured; remove/rename if redundant |
| P2-010 | pending | Audit RSP/sector duplication | Shared exposure measured and reduced/disclosed |
| P2-011 | pending | Audit volatility collinearity | VIX features tested jointly and individually |
| P2-012 | pending | Compare five pillars with three factors | Trend, participation, stress/liquidity candidate evaluated |

### P2-D — Normalize without hiding uncertainty

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P2-013 | pending | Compare range/percentile/z-score transforms | Past-only; crisis and missing-data behavior inspected |
| P2-014 | pending | Add missing-signal shrinkage | Missing evidence reduces reliability and pulls toward neutral |
| P2-015 | pending | Preserve contribution explainability | Normalized totals remain decomposable |

### P2-E — Realism and reproducibility

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P2-016 | pending | Add next-open and next-close execution | Same-close retained for comparison; delay impact reported |
| P2-017 | pending | Use daily equity curves | Intra-hold drawdowns not hidden |
| P2-018 | pending | Pin dataset manifest and hashes | Inputs, symbol coverage, commit, and date reproducible |
| P2-019 | pending | Align costs with rebalance cadence | Turnover and assumptions match strategy behavior |
| P2-020 | pending | Add proportionate multiple-testing controls | Bootstrap, trial count, sensitivity, lockbox minimum; PBO/DSR only for strategy claims |

### P2 release gate

A v7 candidate replaces v6 only when:

- Target and horizon are explicit.
- Report is generated from a pinned dataset manifest.
- Candidate is compared with unchanged v6 and simple baselines.
- Threshold occupancy and stability are acceptable.
- Claims do not exceed out-of-sample evidence.
- Numerical changes appear in a model changelog.

Failure is valid. If no candidate improves the declared objective, retain the
simpler model and publish the negative result.

---

## P3 — Prospective Forecast Log and Self-Grading

Start with the tested EOD score. Treat each additional time as a separate track.

### Forecast record

```json
{
  "model_version": "v6",
  "engine_commit": "<git-sha>",
  "calculated_at": "<ISO-8601>",
  "market_data_as_of": "<ISO-8601>",
  "market_session": "open|close|premarket|afterhours|weekend|holiday",
  "observation_track": "eod|premarket|1000|1200",
  "total_score": 0,
  "decision_band": "...",
  "pillars": {},
  "reliability": {},
  "volatility_budget": {},
  "data_sources": {},
  "input_manifest_hash": "..."
}
```

Outcomes are appended or joined later without mutating the forecast.

### P3-A — Observation tracks

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P3-001 | done | Implement 16:05 EOD track | Durable record on trading days using tested concept |
| P3-002 | pending | Add 09:25 premarket track | Evaluated separately with time-available inputs |
| P3-003 | pending | Add 10:00 early-session track | Partial-day features/time-normalized volume versioned separately |
| P3-004 | pending | Add 12:00 midday track | Not pooled with EOD without stratification |

### P3-B — Predeclare outcomes

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P3-005 | done | Define next-session realized volatility | Formula, bars, missing rules, delay documented |
| P3-006 | done | Define range size and efficiency | Same report definitions or explicit version |
| P3-007 | done | Define favorable/adverse excursion | Reference price and horizon explicit |
| P3-008 | done | Define return and large-move events | Direction separate from conditions interpretation |
| P3-009 | done | Set display sample-size minimums | No premature rolling metrics |

### P3-C — Persistence and auditability

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P3-010 | done | Select durable storage | Render ephemeral filesystem is not called persistence |
| P3-011 | done | Make writes idempotent/recoverable | One record per model/track/session; retry safe |
| P3-012 | done | Add export and audit tooling | Hashes, gaps, and mutation can be checked |
| P3-013 | done | Surface scheduler health | Missed observations and stale jobs visible |

### P3-D — Self-grading UI

| ID | Status | Task | Acceptance criteria |
|---|---|---|---|
| P3-014 | pending | Add “How has this model graded?” | Sample, period, version, uncertainty visible |
| P3-015 | pending | Separate descriptive/predictive metrics | Range calibration not mistaken for alpha |
| P3-016 | pending | Show calibration/stability, not engagement | No gamified streaks or cherry-picking |
| P3-017 | pending | Archive model transitions | Materially different versions not pooled silently |

---

## P4 — Optional Public-Research Hardening

| ID | Status | Task | Trigger |
|---|---|---|---|
| P4-001 | deferred | Versioned releases and changelog | Once v7 begins |
| P4-002 | deferred | `CITATION.cff` and archival release | Research-artifact positioning |
| P4-003 | deferred | Security policy/dependency scanning | Outside users/contributors |
| P4-004 | deferred | Independent methodology review | Strong public performance claims |
| P4-005 | deferred | Legal/compliance review | Commercialization/personalization/brokerage |
| P4-006 | deferred | Formal PBO/Deflated Sharpe analysis | Optimized executable strategy claims |

---

## Recommended Pull Request Sequence

| PR | Scope | Primary files | Dependencies |
|---|---|---|---|
| PR-1 | Label contract and visible bugs | `scoring.py`, `analysis.py`, tests | None |
| PR-2 | Runtime safety and environment | `server.py`, `config.py`, package metadata | None |
| PR-3 | Docs, license, watchlist privacy | README, LICENSE, watchlists, `watchlist.py` | None |
| PR-4 | Evidence-aligned band/persona copy | scoring, analysis, frontend, tests | PR-1 preferred |
| PR-5 | Freshness/reliability contract | data, models, scoring, UI, tests | PR-2 preferred |
| PR-6 | Volatility-budget presentation | config, scoring, UI, docs/tests | PR-5 |
| PR-7 | AI authority/schema hardening | AI, analysis, UI/tests | PR-1, PR-4 |
| PR-8 | Calendar context-only | scoring, replay/report/docs/tests | PR-4 |
| PR-9 | Hysteresis/notification policy | scoring, notify, UI/tests | PR-5 |
| PR-10 | Prospective EOD logging MVP | new module, scheduler, tests | P0/P1 stable |
| Research PR | v7 experiments | research branch only | P0/P1 merged |

PR-1, PR-2, and PR-3 are parallelizable. Later work should rebase after shared
contracts settle.

---

## Agent Collaboration Protocol

### Before starting

1. Read `CLAUDE.md` and this plan.
2. Check the working tree and active branch.
3. Choose task IDs with minimal file overlap.
4. Mark selected tasks `in_progress` in the branch/PR when practical.
5. State dependencies and expected files.

### During implementation

- Put IDs in commits/PRs, e.g. `P0-001/P0-004: repair SKEW contract`.
- Do not expand maintenance into a numerical model change.
- Preserve negative results and document changed assumptions.
- Add/update tests for every contract or behavior change.
- Coordinate before editing files owned by another in-progress task.

### On completion

1. Run applicable validation and record exact commands/results.
2. Mark `done` only after merge, not after local coding.
3. Add a concise plan changelog entry.
4. If blocked, mark `blocked` with the concrete dependency.
5. If evidence changes a decision, update the relevant `D-*` entry explicitly.

### Conflict avoidance

- Contract work lands before broad UI copy work.
- Only one branch at a time changes numerical scoring.
- UI must consume backend truth rather than duplicate it where possible.
- Generated reports are regenerated by canonical scripts, never hand-edited.
- Personal configuration and watchlists remain outside version control.

---

## Global Definition of Done

A task or phase is complete only when applicable conditions hold:

- Behavior is covered by automated tests.
- Public copy matches evidence and avoids unsupported authority.
- Source and freshness semantics are accurate.
- Missing data fails visibly and conservatively.
- Documentation and API contracts agree.
- Accessibility is preserved or improved.
- Model changes include a version and updated validation evidence.
- No personal information, secrets, or machine-local paths are exposed.
- Relevant suites pass on supported runtimes.

---

## Open Questions

| ID | Question | Needed before |
|---|---|---|
| Q-001 | Retain ~7.8% default target or present rounded 8%? | P1-007–P1-009 |
| Q-002 | Browser-local watchlists, generic example, or none on public demo? | P0-025 follow-up |
| Q-003 | Which reliability components belong in v1 and how are they combined? | P1-002 |
| Q-004 | Keep five descriptive pillars or target three factors in v7? | P2-012 |
| Q-005 | Which outcome is primary for each horizon? | P2-001 |
| Q-006 | ~~Where should public-demo forecast records persist?~~ Resolved: local-first JSONL; the Render demo is explicitly non-persistent (`/health` flags it) | P3-010 |
| Q-007 | Keep classic UI supported or archive it? | Major P1 UI work |

---

## Plan Changelog

| Date | Version | Change | Author/agent |
|---|---|---|---|
| 2026-07-11 | 1.0 | Consolidated repository audit and independent review convergence | Codex |
| 2026-07-12 | 1.1 | P0 complete — PRs #50–#53, #55 merged; all P0-001..P0-026 done | Claude |
| 2026-07-12 | 1.2 | PR-5 merged (#56) — P1-001..P1-006 done; Q-001 resolved: keep calibrated 7.8% default, rounded presets in UI | Claude |
| 2026-07-12 | 1.3 | PR-6 merged (#57) — P1-007..P1-011 done; conditions-band positions replace exposure directives | Claude |
| 2026-07-12 | 1.4 | PR-7 merged (#58) — P1-019..P1-024 done. PR-8 introduces model v6.1: calendar overlays context-only, aligning live model with the replayed one | Claude |
| 2026-07-12 | 1.5 | PR-8 merged (#59) — P1-025..P1-028 done. PR-9: band hysteresis (3 pts), SCORE_NOISE_DELTA_1D=14 derived from replay (median daily move), band-change-only push default | Claude |
| 2026-07-12 | 1.6 | PR-9 merged (#60) — P1-029..P1-032 done. PR-10: prospective forecast log MVP (P3-001, P3-005..P3-013) — EOD track, predeclared outcomes (docs/prospective-log.md), idempotent JSONL + hash audit, /health visibility; Q-006 resolved local-first. CI gap closed: notify/watchlist/claims/ai-lens suites now enumerated | Claude |
| 2026-07-12 | 1.7 | #61/#62/#63 merged (forecast log, eod_job.py standalone runner, RENDER-only production detection). Local launchd agents live (server + EOD backup). P1-C shipped: P1-012..P1-018 done — monochrome+amber palette, radar→evidence bars with missing states, prominent no-timing-edge disclaimer, monochrome data bars, watchlist labels neutralized, collapsible lens cards | Claude |
