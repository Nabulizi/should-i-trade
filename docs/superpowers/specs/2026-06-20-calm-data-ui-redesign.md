# Calm Data UI Redesign — Design Spec
**Date:** 2026-06-20  
**Branch:** `feature/minimal-calm-ui`  
**Approach:** B — Calm Data

---

## Problem

The current UI is built for a power user who already understands the system. The primary audience for the live demo at `should-i-trade.onrender.com` is broader: non-technical traders who need to quickly understand **why the score is what it is**. The current layout buries the pillar breakdown under a scrolling ticker, a dense header, a three-column hero section, and a futures card. The visual language (two competing accent colors, 9px text, pure terminal aesthetic) adds friction rather than clarity.

---

## Goals

1. Make the **5-pillar breakdown the first meaningful content** a user sees.
2. Reduce visual noise without losing the market-tool character.
3. Serve the live demo visitor who has no prior familiarity with the system.
4. Meet WCAG 2.2 AA contrast minimums throughout.
5. Maintain all existing functionality — nothing is deleted from the app, only reorganized or collapsed.

---

## Information Architecture

### New page order (top to bottom)

| Section | Visibility | Notes |
|---|---|---|
| Header | Always | Compact — see header spec |
| Score + Posture strip | Always | Replaces the old 3-col hero |
| Futures card | Always | Compact, market-session context |
| **5 Pillar cards** | **Always — HERO** | First major content block |
| Sparkline history | Always | Score history inline |
| Sector breadth | Always | Breadth Under the Surface |
| Trading Desk Roundtable | **Collapsed by default** | Expand toggle |
| Watchlist Health | **Collapsed by default** | Expand toggle |

### Removed from main view

| Element | Disposition |
|---|---|
| Scrolling ticker bar | **Removed** — ambient noise, no decision value |
| "Execution Window" card | **Removed** — redundant with posture badge |
| "Scoring Weights" card | **Moved to settings drawer** — what-if tool belongs in settings |
| FOMC/econ events row | **Condensed** — one line inline in header |
| "Suggested Exposure" side card | **Merged** — text absorbed into posture badge label |
| "Quality Terminal v6" subtitle | **Removed** — version noise |
| Timestamps + "next refresh" countdown | **Removed** — not decision-relevant for broader audience |
| Alert bell button | **Removed** — feature not prominent enough to earn header space |
| Copy snapshot button | **Removed** — power-user feature moved to ⋯ menu or settings |

---

## Header Spec

**Left side:** `[Logo + SHOULD I TRADE?]` · `[Score badge: 72 · CONSTRUCTIVE]` · `[FOMC in 38d]`

**Right side:** `[Theme toggle]` · `[↺ Refresh]` · `[⚙ Settings]`

- Max 3 controls on the right.
- The score+posture badge in the header gives users the answer at a glance before scrolling.
- FOMC/econ proximity stays visible but takes one slot, not a full row.

---

## Score + Posture Strip

Replaces the old 3-column hero (decision card + score circle + exposure card).

- Single horizontal strip: `Score circle (80px)` · `[Score number]` · `[Posture badge: CONSTRUCTIVE]` · `[Exposure text: Standard exposure]` · `[Caveat: not advice · not a return signal]`
- Score circle kept — it's visually distinctive and immediately communicates magnitude.
- Strip is compact (64–80px height) so pillars reach above the fold faster.

---

## Pillar Cards — Hero Section

The 5 pillar cards are the primary content. Changes from current:

| Property | Current | New |
|---|---|---|
| Score number size | 20px | 40px |
| Progress bar height | 3px | 6px |
| Card padding | 14px | 20px |
| Label font | Fira Code | Inter |
| Value/number font | Fira Code | Fira Code (kept) |
| "WHY THIS SCORE?" expand | Kept | Kept |
| Grid | 5-col on desktop | 5-col desktop / 2-col tablet / 1-col mobile |

---

## Visual Language

### Typography

- **Labels, headings, copy:** Inter (or `system-ui` fallback)
- **Numbers, scores, prices, tickers:** Fira Code (kept for numerical identity)
- **Type scale:** 10px (label) / 14px (body) / 28px (display) — 3 sizes only

### Color tokens (updated)

| Token | Current | New |
|---|---|---|
| `--bg` | `#020617` | `#0a0f14` |
| `--surface` | `#0e1419` + `#131b22` | `#111820` (one surface) |
| `--border` | `#1a2530` | `#1e2b38` |
| `--accent` | `#00b0ff` + `#7c4dff` | `#3b82f6` (one accent) |
| `--text` | `#e0e8f0` | `#dce6f0` |
| `--muted` | `#7e94a9` | `#6b7a8d` |
| Status colors | unchanged | unchanged |

### Spacing

- Base unit: 8px
- Card padding: 20px (was 14px)
- Page gutter: 24px (was 16px)
- Section gap: 16px (was 14px)

### Shape

- Card `border-radius`: 4px (was 6px) — subtler
- No box shadows
- No gradients
- Borders over backgrounds for separation

---

## Collapsed Sections

Roundtable and Watchlist start collapsed. Both get a consistent expand toggle:

```
[▶ Trading Desk Roundtable]     [Run Rule-Based Read]
```

Clicking the row expands the content. State persists in `localStorage`. This reduces initial page weight by roughly 40% of the DOM.

---

## Futures Card (kept visible)

Stays in the page but compact: one-line tone summary + futures grid. No changes to content — only spacing/typography updated.

---

## Accessibility

- All text ≥ 12px rendered (10px labels reserved for supplementary metadata only).
- Focus rings visible on all interactive elements: `outline: 2px solid var(--accent); outline-offset: 2px`.
- `prefers-reduced-motion`: all CSS transitions wrapped in `@media (prefers-reduced-motion: no-preference)`.
- Color is never the only differentiator — labels accompany all status colors.
- `aria-expanded` on all collapse toggles.

---

## Files Changed

| File | Change |
|---|---|
| `static/app.css` | Typography tokens, color tokens, spacing, pillar card sizing, ticker removal, header simplification, collapsed section styles |
| `should-i-trade-v6.html` | Remove ticker DOM, simplify header, replace 3-col hero with strip, add collapse toggles for roundtable + watchlist, move scoring weights to settings drawer |
| `static/app.js` | Collapse/expand logic for roundtable + watchlist, remove ticker rendering, remove countdown/timestamp update logic |

---

## Out of Scope

- No changes to Python backend, scoring logic, or API.
- No changes to light theme (addressed as a follow-on).
- No new dependencies.
- The AI roundtable feature is unchanged — just collapsed by default.

---

## Success Criteria

- A first-time visitor on desktop can read the score, posture, and all 5 pillar scores without scrolling.
- All interactive elements have visible focus states.
- No element is below WCAG AA contrast ratio.
- Mobile layout (390px) shows pillar cards stacked clearly.
- All existing Python and JS tests pass unchanged.
