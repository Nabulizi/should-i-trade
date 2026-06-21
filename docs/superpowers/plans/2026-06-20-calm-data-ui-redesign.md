# Calm Data UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Should I Trade? dashboard from a Bloomberg-terminal aesthetic to a calm, accessible experience where the 5-pillar breakdown is the first meaningful content a user sees.

**Architecture:** All changes are frontend-only: `static/app.css` (tokens, spacing, typography), `should-i-trade-v6.html` (DOM restructure), `static/app.js` (null guards for removed DOM elements, collapse logic). No backend changes.

**Tech Stack:** Vanilla JS (ES modules), CSS custom properties, Vitest for JS unit tests, Python unittest for backend

---

## Pre-flight

- [ ] Confirm you are on branch `feature/minimal-calm-ui`
- [ ] Run `npm test` — all JS tests must pass before you start

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass (scoreColor, colorClass, decisionForScore, chgStr, weight scenarios)

---

## Task 1: CSS Design Tokens + Inter Font

**Files:**
- Modify: `should-i-trade-v6.html` (Google Fonts link)
- Modify: `static/app.css` (`:root` block, `body` rule)

### Step 1: Update the Google Fonts `<link>` to also load Inter

In `should-i-trade-v6.html`, find:
```html
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Replace with:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
```

### Step 2: Update `:root` tokens in `static/app.css`

Find the entire `:root` block (lines 1–16 of app.css):
```css
:root {
    --bg:      #020617;
    --surface: #0e1419;
    --surface2:#131b22;
    --border:  #1a2530;
    --border2: #243342;
    --green:   #00e676;
    --yellow:  #ffd740;
    --orange:  #ffaa00;
    --red:     #ff1744;
    --text:    #e0e8f0;
    --muted:   #7e94a9;
    --muted2:  #8aa0b4;
    --accent:  #00b0ff;
    --accent2: #7c4dff;
  }
```

Replace with:
```css
:root {
    --bg:      #0a0f14;
    --surface: #111820;
    --surface2:#111820;
    --border:  #1e2b38;
    --border2: #1e2b38;
    --green:   #00e676;
    --yellow:  #ffd740;
    --orange:  #ffaa00;
    --red:     #ff1744;
    --text:    #dce6f0;
    --muted:   #6b7a8d;
    --muted2:  #6b7a8d;
    --accent:  #3b82f6;
    --accent2: #3b82f6;
    --sans:    system-ui, -apple-system, 'Inter', sans-serif;
  }
```

### Step 3: Update `body` font-family in `static/app.css`

Find:
```css
  body { background: var(--bg); color: var(--text); font-family: 'Fira Code', 'SF Mono', Menlo, monospace; font-size: 13px; }
```

Replace with:
```css
  body { background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 13px; }
```

### Step 4: Run JS tests — should still pass

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass (no DOM dependency in the tests)

### Step 5: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add should-i-trade-v6.html static/app.css
git commit -m "style: update design tokens — warmer bg, single accent, Inter font"
```

---

## Task 2: Remove Ticker Bar

**Files:**
- Modify: `should-i-trade-v6.html` (remove `.ticker-wrap` div)
- Modify: `static/app.css` (remove ticker CSS rules)
- Modify: `static/app.js` (add null guard in `renderTicker`, remove call from `load()`)

### Step 1: Remove the ticker DOM from `should-i-trade-v6.html`

Find and delete:
```html
<!-- TICKER -->
<div class="ticker-wrap"><div class="ticker-inner" id="ticker"></div></div>
```

### Step 2: Remove ticker CSS from `static/app.css`

Find and delete the entire `/* ── TICKER ── */` block:
```css
  /* ── TICKER ── */
  .ticker-wrap { background: #050810; border-bottom: 1px solid var(--border); overflow: hidden; white-space: nowrap; height: 28px; display: flex; align-items: center; }
  .ticker-inner { display: inline-block; animation: scroll 90s linear infinite; }
  .ticker-inner:hover { animation-play-state: paused; }
  @keyframes scroll { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
  .tick { display: inline-block; padding: 0 18px; font-size: 11px; font-weight: 600; }
  .tick .sym { color: var(--muted); margin-right: 4px; }
  .tick .px  { color: var(--text); }
  .tick.up   .chg { color: var(--green); }
  .tick.dn   .chg { color: var(--red); }
```

### Step 3: Add null guard in `renderTicker` in `static/app.js`

Find:
```js
function renderTicker(items) {
  const doubled = [...items, ...items];
  $('ticker').innerHTML = doubled.map(t => `
```

Replace with:
```js
function renderTicker(items) {
  if (!$('ticker')) return;
  const doubled = [...items, ...items];
  $('ticker').innerHTML = doubled.map(t => `
```

### Step 4: Remove `renderTicker` call from `load()` in `static/app.js`

Inside the `requestAnimationFrame` callback in `load()`, find:
```js
      renderTicker(raw.ticker || []);
```

Delete that line.

### Step 5: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 6: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add should-i-trade-v6.html static/app.css static/app.js
git commit -m "feat: remove scrolling ticker bar"
```

---

## Task 3: Simplify Header

**Files:**
- Modify: `should-i-trade-v6.html` (remove subtitle, timestamps, countdown, alert-btn, copy button; add `#header-score`)
- Modify: `static/app.js` (null guards for removed elements; update `renderHeader` + `renderHero` to write to `#header-score`)

### Step 1: Replace the header HTML in `should-i-trade-v6.html`

Find the entire `<!-- HEADER -->` block:
```html
<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <span class="logo"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px" aria-hidden="true"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>SHOULD I TRADE?</span>
    <span class="subtitle">Quality Terminal v6</span>
    <span class="mkt-badge" id="mkt-badge"><span class="dot"></span><span id="mkt-label">—</span></span>
    <span class="fomc-badge" id="fomc-badge">FOMC <span class="date" id="fomc-text">—</span></span>
  </div>
  <div class="header-right">
    <span class="ts" id="et-time">—</span>
    <span class="ts" id="data-ts">—</span>
    <span class="countdown" id="countdown">next refresh in —</span><span id="refresh-dot" title="Updating…"></span>
    <button class="btn" onclick="copySnapshot()" title="Copy snapshot to clipboard (journal)" aria-label="Copy snapshot to clipboard">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
      <button class="btn" id="alert-btn" onclick="toggleAlerts()" title="Score zone change notifications" aria-label="Toggle score alerts" style="opacity:0.45">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
      </button>
      <button class="btn" onclick="toggleTheme()" id="theme-btn" title="Toggle dark/light theme" aria-label="Toggle dark/light theme">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      </button>
      <button class="btn" onclick="toggleSettings()" title="Settings (S)" aria-label="Open settings">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      </button>
      <button class="btn" onclick="load(true)" aria-label="Refresh data">↺ REFRESH</button>
  </div>
</div>
```

Replace with:
```html
<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <span class="logo"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px" aria-hidden="true"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>SHOULD I TRADE?</span>
    <span class="mkt-badge" id="mkt-badge"><span class="dot"></span><span id="mkt-label">—</span></span>
    <span class="fomc-badge" id="fomc-badge">FOMC <span class="date" id="fomc-text">—</span></span>
    <span class="header-score" id="header-score" aria-live="polite"></span>
  </div>
  <div class="header-right">
    <span id="refresh-dot" title="Updating…"></span>
    <button class="btn" onclick="toggleTheme()" id="theme-btn" title="Toggle dark/light theme" aria-label="Toggle dark/light theme">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
    </button>
    <button class="btn" onclick="toggleSettings()" title="Settings" aria-label="Open settings">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    </button>
    <button class="btn" onclick="load(true)" aria-label="Refresh data">↺ REFRESH</button>
  </div>
</div>
```

### Step 2: Add `.header-score` CSS in `static/app.css`

After the `.fomc-badge` rules, add:
```css
  .header-score { font-size: 12px; font-weight: 700; font-family: 'Fira Code', monospace; color: var(--muted); letter-spacing: 0.5px; }
  .header-score.loaded { color: var(--text); }
```

Also add CSS for hiding the removed `.subtitle` class (safe — it no longer exists in DOM but belt-and-suspenders):
```css
  .subtitle { display: none; }
```

And keep `#refresh-dot` styles but hide `#countdown` (it is gone from DOM — its setInterval still runs but now writes to null):
```css
  #refresh-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); display: inline-block; opacity: 0; transition: opacity 0.3s; vertical-align: middle; }
  #refresh-dot.active { opacity: 1; animation: pulse 1s infinite; }
```

### Step 3: Add null guards for removed elements in `static/app.js`

In `renderHeader(d)`, find:
```js
  $('et-time').textContent = mkt.et_time ? `${mkt.et_date} · ${mkt.et_time}` : '—';
```

Replace with (null guard + remove data-ts update):
```js
  const etEl = $('et-time'); if (etEl) etEl.textContent = mkt.et_time ? `${mkt.et_date} · ${mkt.et_time}` : '—';
```

Find:
```js
  $('data-ts').textContent = d.timestamp ? `updated ${d.timestamp}` : '';
```

Replace with:
```js
  const dtsEl = $('data-ts'); if (dtsEl) dtsEl.textContent = d.timestamp ? `updated ${d.timestamp}` : '';
```

### Step 4: Add null guard in `tickCountdown` in `static/app.js`

Find:
```js
function tickCountdown() {
  if (!_nextRefreshAt) { $('countdown').textContent = ''; return; }
  const left = Math.max(0, _nextRefreshAt - Date.now());
  if (left === 0) {
    _nextRefreshAt = 0;
    $('countdown').textContent = 'refreshing…';
    load(false);
    return;
  }
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  $('countdown').textContent = `next refresh in ${m}:${s.toString().padStart(2, '0')}`;
}
```

Replace with:
```js
function tickCountdown() {
  const cdEl = $('countdown');
  if (!_nextRefreshAt) { if (cdEl) cdEl.textContent = ''; return; }
  const left = Math.max(0, _nextRefreshAt - Date.now());
  if (left === 0) {
    _nextRefreshAt = 0;
    if (cdEl) cdEl.textContent = 'refreshing…';
    load(false);
    return;
  }
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  if (cdEl) cdEl.textContent = `next refresh in ${m}:${s.toString().padStart(2, '0')}`;
}
```

### Step 5: Update `renderHero` to populate `#header-score`

At the end of the `renderHero(d)` function, just before the closing `}`, add:
```js
  // Update header score badge
  const headerScore = $('header-score');
  if (headerScore) {
    const invalidData = d.data_quality?.valid === false;
    headerScore.textContent = invalidData ? '— · DATA UNAVAILABLE' : `${s} · ${d.decision}`;
    headerScore.className = 'header-score loaded';
    headerScore.style.color = invalidData ? 'var(--muted)' : scoreColor(s);
  }
```

### Step 6: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 7: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add should-i-trade-v6.html static/app.css static/app.js
git commit -m "feat: simplify header — 3 controls, score badge, remove noise"
```

---

## Task 4: Replace 3-Column Hero with Compact Score Strip

**Files:**
- Modify: `should-i-trade-v6.html` (replace hero div)
- Modify: `static/app.css` (remove old hero CSS, add `.score-strip` CSS)
- Modify: `static/app.js` (null guard for `#pillars-mini`)

### Step 1: Replace the hero HTML in `should-i-trade-v6.html`

Inside `<div id="content" style="display:none">` → `<div class="main">`, find the entire `<!-- HERO -->` block:
```html
    <!-- HERO -->
    <div class="hero">
      <div class="decision-card">
        <div class="decision-label">Risk Posture</div>
        <div class="decision-badge" id="decision-badge">—</div>
        <div class="decision-sub" id="decision-sub">Swing Trading</div>
        <div class="decision-context" id="decision-context" style="display:none"></div>
      </div>

      <div class="hero-mid">
        <div class="score-circle-wrap">
          <div class="score-circle">
            <svg width="110" height="110" viewBox="0 0 110 110">
              <circle class="track" cx="55" cy="55" r="46"/>
              <circle class="fill" id="score-arc" cx="55" cy="55" r="46" stroke-dasharray="289" stroke-dashoffset="289"/>
            </svg>
            <div class="score-num">
              <div class="val" id="score-val">—</div>
              <div class="tot">/ 100</div>
            </div>
          </div>
          <div class="score-label">Total Score</div>
          <div class="score-caveat">not advice · not a return signal</div>
          <div class="score-freshness" id="score-freshness"></div>
          <div class="streak-badge-wrap" style="display:none"></div>
        </div>
        <div class="pillars-mini" id="pillars-mini"></div>
      </div>

      <div class="pos-card">
        <div class="pos-label">Suggested Exposure</div>
        <div class="pos-icon" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="pos-text" id="pos-text">—</div>
        <div class="pos-sub">Drawdown-timed</div>
      </div>
    </div>
```

Replace with:
```html
    <!-- SCORE STRIP -->
    <div class="score-strip">
      <div class="strip-circle">
        <svg width="80" height="80" viewBox="0 0 110 110">
          <circle class="track" cx="55" cy="55" r="46"/>
          <circle class="fill" id="score-arc" cx="55" cy="55" r="46" stroke-dasharray="289" stroke-dashoffset="289"/>
        </svg>
        <div class="score-num">
          <div class="val" id="score-val">—</div>
          <div class="tot">/ 100</div>
        </div>
      </div>
      <div class="strip-info">
        <div class="strip-posture">
          <span class="decision-badge" id="decision-badge">—</span>
          <span class="strip-exposure" id="pos-text">—</span>
        </div>
        <div class="decision-context" id="decision-context" style="display:none"></div>
        <div class="score-freshness" id="score-freshness"></div>
        <div class="streak-badge-wrap" style="display:none"></div>
      </div>
      <div class="strip-caveat">not advice · not a return signal</div>
    </div>
    <!-- Hidden legacy IDs kept for JS compatibility -->
    <div id="pillars-mini" style="display:none" aria-hidden="true"></div>
```

### Step 2: Add `.score-strip` CSS to `static/app.css`

After the `.main` rule, add the new strip CSS (replacing the old `.hero` block — delete the old `.hero`, `.decision-card`, `.pos-card`, `.hero-mid`, `.score-circle-wrap`, `.pillars-mini`, `.pillar-mini` rules and add):

Find and delete the old hero CSS block (from `.hero {` to the last `.pillar-mini .pm-label` line):
```css
  .hero { display: grid; grid-template-columns: clamp(185px, 14vw, 225px) 1fr clamp(140px, 11vw, 170px); gap: 14px; align-items: stretch; }
  .decision-card, .pos-card, .score-wrap-card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 18px; text-align: center; display: flex; flex-direction: column; justify-content: center; min-width: 0; overflow: hidden; }
  .decision-card { justify-content: flex-start; padding-top: 16px; }
  .decision-label, .pos-label { font-size: 10px; letter-spacing: 2px; color: var(--muted); text-transform: uppercase; margin-bottom: 8px; }
  .decision-badge { font-size: clamp(14px, 1.4vw, 22px); font-weight: 800; letter-spacing: clamp(0px, 0.08vw, 1px); margin-bottom: 4px; white-space: nowrap; }
  .decision-sub { font-size: 10px; color: var(--muted); }
  .pos-icon { font-size: 26px; margin-bottom: 4px; }
  .pos-text { font-size: 13px; font-weight: 700; letter-spacing: 1px; }
  .pos-sub  { font-size: 10px; color: var(--muted); margin-top: 4px; }

  .hero-mid { display: flex; align-items: center; justify-content: center; gap: 28px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 14px 18px; min-width: 0; overflow: hidden; }
  .score-circle-wrap { display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .score-circle { position: relative; width: 110px; height: 110px; }
  .score-circle svg { transform: rotate(-90deg); }
  .score-circle .track { fill: none; stroke: var(--border); stroke-width: 8; }
  .score-circle .fill  { fill: none; stroke-width: 8; stroke-linecap: round; transition: stroke-dashoffset 1s ease; }
  .score-num { position: absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; }
  .score-num .val { font-size: 28px; font-weight: 800; }
  .score-num .tot { font-size: 10px; color: var(--muted); }
  .score-label { font-size: 10px; letter-spacing: 2px; color: var(--muted); text-transform: uppercase; }
  .score-caveat { font-size: 9px; color: var(--muted); letter-spacing: 0.3px; margin-top: 3px; opacity: 0.7; }
  .score-freshness { font-size: 9px; color: var(--muted); letter-spacing: 0.3px; margin-top: 1px; }

  .pillars-mini { display: flex; gap: 22px; }
  .pillar-mini { display: flex; flex-direction: column; align-items: center; gap: 5px; }
  .pillar-mini .pm-score { font-size: 22px; font-weight: 700; }
  .pillar-mini .pm-bar { width: 58px; height: 3px; background: var(--border); border-radius: 2px; overflow: hidden; }
  .pillar-mini .pm-fill { height: 100%; border-radius: 2px; transition: width 1s ease; }
  .pillar-mini .pm-label { font-size: 10px; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
```

Replace with:
```css
  /* ── SCORE STRIP ── */
  .score-strip { display: flex; align-items: center; gap: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 16px 20px; }
  .strip-circle { position: relative; width: 80px; height: 80px; flex-shrink: 0; }
  .strip-circle svg { transform: rotate(-90deg); display: block; }
  .strip-circle .track { fill: none; stroke: var(--border); stroke-width: 8; }
  .strip-circle .fill  { fill: none; stroke-width: 8; stroke-linecap: round; transition: stroke-dashoffset 1s ease; }
  .score-num { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); text-align: center; }
  .score-num .val { font-size: 24px; font-weight: 800; font-family: 'Fira Code', monospace; line-height: 1; }
  .score-num .tot { font-size: 9px; color: var(--muted); font-family: 'Fira Code', monospace; }
  .strip-info { flex: 1; min-width: 0; }
  .strip-posture { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
  .decision-badge { font-size: 18px; font-weight: 800; letter-spacing: 0.5px; white-space: nowrap; font-family: 'Fira Code', monospace; }
  .strip-exposure { font-size: 13px; color: var(--muted); font-weight: 500; }
  .score-freshness { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .strip-caveat { font-size: 10px; color: var(--muted); opacity: 0.6; white-space: nowrap; align-self: flex-end; }
  /* Keep decision-context styles */
  .decision-context { font-size: 12px; color: var(--muted); margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
  .dc-row { display: flex; align-items: center; gap: 8px; }
  .dc-label { font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); min-width: 70px; }
  .dc-posture { font-size: 12px; color: var(--text); line-height: 1.5; }
  .confidence-bar { display: flex; gap: 3px; }
  .conf-seg { width: 14px; height: 4px; border-radius: 2px; }
  .streak-badge { font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: 600; }
  .streak-badge.streak-up { background: rgba(0,230,118,0.12); color: var(--green); }
  .streak-badge.streak-down { background: rgba(255,23,68,0.10); color: var(--red); }
```

### Step 3: Add null guard for `#pillars-mini` in `static/app.js`

In `renderHero`, find:
```js
  $('pillars-mini').innerHTML = `<div class="radar-wrap">${buildRadarChart(d.pillars)}</div>`;
```

Replace with:
```js
  const pmEl = $('pillars-mini');
  if (pmEl) pmEl.innerHTML = `<div class="radar-wrap">${buildRadarChart(d.pillars)}</div>`;
```

### Step 4: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 5: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add should-i-trade-v6.html static/app.css static/app.js
git commit -m "feat: replace 3-col hero with compact score strip"
```

---

## Task 5: Pillar Card Visual Upgrades

**Files:**
- Modify: `static/app.css` (pillar card sizing)

### Step 1: Update pillar card CSS

In `static/app.css`, find:
```css
  .pillars-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
  .pillar-card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 14px; display: flex; flex-direction: column; }
  .pillar-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
  .pillar-name { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; }
  .pillar-score-badge { font-size: 20px; font-weight: 800; }
  .pillar-bar { height: 3px; background: var(--border); border-radius: 2px; margin-bottom: 12px; overflow: hidden; }
  .pillar-bar-fill { height: 100%; border-radius: 2px; transition: width 1s ease; }
  .metric-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; min-height: 16px; }
  .metric-key { color: var(--muted); font-size: 10px; }
  .metric-val { font-size: 10px; font-weight: 600; display: flex; align-items: center; gap: 5px; }
```

Replace with:
```css
  .pillars-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
  .pillar-card { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 20px; display: flex; flex-direction: column; }
  .pillar-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
  .pillar-name { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted); }
  .pillar-score-badge { font-size: 40px; font-weight: 800; font-family: 'Fira Code', monospace; line-height: 1; }
  .pillar-bar { height: 6px; background: var(--border); border-radius: 3px; margin-bottom: 14px; overflow: hidden; }
  .pillar-bar-fill { height: 100%; border-radius: 3px; transition: width 1s ease; }
  .metric-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 7px; min-height: 18px; }
  .metric-key { color: var(--muted); font-size: 11px; }
  .metric-val { font-size: 11px; font-weight: 600; display: flex; align-items: center; gap: 5px; font-family: 'Fira Code', monospace; }
```

### Step 2: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 3: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add static/app.css
git commit -m "style: pillar cards — larger score (40px), wider bar (6px), more padding"
```

---

## Task 6: Collapse Roundtable + Watchlist Sections

**Files:**
- Modify: `should-i-trade-v6.html` (wrap sections in collapse containers)
- Modify: `static/app.css` (collapse toggle styles)
- Modify: `static/app.js` (collapse/expand logic, defer auto-run)

### Step 1: Add `toggleSection` function and helpers to `static/app.js`

Just before the `/* ── ROUNDTABLE ──` comment, add:

```js
/* ── COLLAPSIBLE SECTIONS ──────────────────────────────── */
const _SECTION_DEFAULTS = { roundtable: false, watchlist: false };

function _sectionExpanded(id) {
  try { const v = localStorage.getItem(`section_${id}`); return v === null ? _SECTION_DEFAULTS[id] : v === 'true'; }
  catch { return _SECTION_DEFAULTS[id]; }
}

function toggleSection(id) {
  const body = document.getElementById(`section-body-${id}`);
  const btn  = document.getElementById(`section-toggle-${id}`);
  if (!body || !btn) return;
  const nowOpen = body.classList.toggle('section-open');
  btn.setAttribute('aria-expanded', String(nowOpen));
  btn.querySelector('.toggle-chevron').style.transform = nowOpen ? 'rotate(90deg)' : '';
  try { localStorage.setItem(`section_${id}`, String(nowOpen)); } catch {}
  if (nowOpen && id === 'roundtable' && !document.querySelector('.persona-card')) runRoundtable(true);
  if (nowOpen && id === 'watchlist' && !_watchlistData) loadWatchlistHealth();
}

function _initSection(id) {
  const body = document.getElementById(`section-body-${id}`);
  const btn  = document.getElementById(`section-toggle-${id}`);
  if (!body || !btn) return;
  const open = _sectionExpanded(id);
  if (open) body.classList.add('section-open');
  btn.setAttribute('aria-expanded', String(open));
  btn.querySelector('.toggle-chevron').style.transform = open ? 'rotate(90deg)' : '';
}
```

### Step 2: Replace the roundtable HTML in `should-i-trade-v6.html`

Find:
```html
    <!-- ROUNDTABLE -->
    <div class="roundtable-section">
      <div class="roundtable-head">
        <span class="roundtable-title"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:4px" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>Trading Desk Roundtable</span>
        <button class="btn" id="rt-btn" onclick="runRoundtable()" aria-label="Generate rule-based desk read"><svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="vertical-align:-1px;margin-right:3px"><polygon points="5 3 19 12 5 21 5 3"/></svg>Rule-Based Read</button>
        <button class="btn btn-ai" id="rt-ai-btn" onclick="runRoundtable(false, true)" aria-label="Run AI analysis — 5 specialist agents, approximately 10 seconds"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-1px;margin-right:3px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>AI Analysis</button>
      </div>
      <div id="roundtable-grid" class="roundtable-grid"></div>
    </div>
```

Replace with:
```html
    <!-- ROUNDTABLE -->
    <div class="collapsible-section">
      <button class="section-toggle" id="section-toggle-roundtable" onclick="toggleSection('roundtable')" aria-expanded="false" aria-controls="section-body-roundtable">
        <span class="toggle-chevron" aria-hidden="true">▶</span>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        Trading Desk Roundtable
      </button>
      <div id="section-body-roundtable" class="section-body">
        <div class="roundtable-head">
          <button class="btn" id="rt-btn" onclick="runRoundtable()" aria-label="Generate rule-based desk read"><svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="vertical-align:-1px;margin-right:3px"><polygon points="5 3 19 12 5 21 5 3"/></svg>Rule-Based Read</button>
          <button class="btn btn-ai" id="rt-ai-btn" onclick="runRoundtable(false, true)" aria-label="Run AI analysis — 5 specialist agents, approximately 10 seconds"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-1px;margin-right:3px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>AI Analysis</button>
        </div>
        <div id="roundtable-grid" class="roundtable-grid"></div>
      </div>
    </div>
```

### Step 3: Replace the watchlist HTML in `should-i-trade-v6.html`

Find:
```html
    <!-- WATCHLIST HEALTH -->
    <div class="card watch-card">
      <div class="card-title"><span class="icon-label"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>Watchlist Health</span> <span class="watch-meta" id="watchlist-meta">TradingView export</span>
        <select id="watchlist-select" style="margin-left:8px;font-size:10px;background:var(--bg2);color:var(--fg);border:1px solid var(--border);border-radius:3px;padding:1px 4px;cursor:pointer;" aria-label="Select watchlist file" onchange="onWatchlistChange()"></select>
      </div>
      <div id="watchlist-health">
        <div style="color:var(--muted);font-size:10px;">Loading watchlist…</div>
      </div>
    </div>
```

Replace with:
```html
    <!-- WATCHLIST HEALTH -->
    <div class="collapsible-section">
      <button class="section-toggle" id="section-toggle-watchlist" onclick="toggleSection('watchlist')" aria-expanded="false" aria-controls="section-body-watchlist">
        <span class="toggle-chevron" aria-hidden="true">▶</span>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        Watchlist Health
        <span class="watch-meta" id="watchlist-meta"></span>
        <select id="watchlist-select" style="font-size:10px;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:3px;padding:1px 4px;cursor:pointer;" aria-label="Select watchlist file" onchange="onWatchlistChange()" onclick="event.stopPropagation()"></select>
      </button>
      <div id="section-body-watchlist" class="section-body">
        <div id="watchlist-health">
          <div style="color:var(--muted);font-size:11px;">Click to load watchlist…</div>
        </div>
      </div>
    </div>
```

### Step 4: Add collapsible CSS to `static/app.css`

Add after the `.roundtable-section` CSS block (or at end of file before media queries):

```css
  /* ── COLLAPSIBLE SECTIONS ── */
  .collapsible-section { border: 1px solid var(--border); border-radius: 4px; background: var(--surface); overflow: hidden; }
  .section-toggle { width: 100%; display: flex; align-items: center; gap: 8px; padding: 14px 20px; background: transparent; border: none; color: var(--text); font-size: 12px; font-weight: 700; letter-spacing: 0.5px; cursor: pointer; text-align: left; font-family: var(--sans); }
  .section-toggle:hover { background: rgba(255,255,255,0.03); }
  .section-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .toggle-chevron { font-size: 9px; color: var(--muted); transition: transform 0.2s; display: inline-block; }
  .section-body { display: none; padding: 0 20px 20px; }
  .section-body.section-open { display: block; }
  .roundtable-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding-top: 4px; }
```

### Step 5: Prevent auto-run of roundtable on first load in `static/app.js`

In the `load()` function, find:
```js
    if (isManual || isFirst || !document.querySelector('.persona-card')) {
      setTimeout(() => runRoundtable(true), 400);
    }
```

Replace with:
```js
    if ((isManual || isFirst) && _sectionExpanded('roundtable')) {
      setTimeout(() => runRoundtable(true), 400);
    }
```

### Step 6: Prevent auto-load of watchlist unless expanded in `static/app.js`

In `load()`, find:
```js
    if (isManual || isFirst) loadWatchlistHealth();
```

Replace with:
```js
    if ((isManual || isFirst) && _sectionExpanded('watchlist')) loadWatchlistHealth();
```

### Step 7: Initialize sections after first load in `static/app.js`

In the `requestAnimationFrame` callback inside `load()`, after `if (isFirst) { $('loading').style.display = 'none'; $('content').style.display = 'block'; }`, add:

```js
      if (isFirst) {
        _initSection('roundtable');
        _initSection('watchlist');
      }
```

Make the block look like:
```js
      if (isFirst) {
        $('loading').style.display = 'none';
        $('content').style.display = 'block';
        _initSection('roundtable');
        _initSection('watchlist');
      }
```

### Step 8: Expose `toggleSection` on window in `static/app.js`

In the window assignments block at the bottom of app.js, find:
```js
  window.copySnapshot           = copySnapshot;
```

After it add:
```js
  window.toggleSection          = toggleSection;
```

### Step 9: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 10: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add should-i-trade-v6.html static/app.css static/app.js
git commit -m "feat: collapse roundtable and watchlist sections by default"
```

---

## Task 7: Reorganize Bottom Row — Remove Execution Window, Make Sparkline Standalone, Move Weights to Settings Drawer

**Files:**
- Modify: `should-i-trade-v6.html` (remove exec-window card, extract sparkline, add weights to settings)
- Modify: `static/app.css` (update bottom-row grid, add standalone sparkline card)
- Modify: `static/app.js` (null guard for `$('exec-window')`)

### Step 1: Add null guard for `$('exec-window')` in `static/app.js`

In `renderExecution`, find (line ~497):
```js
  $('exec-window').innerHTML = checks.map(c => {
```

Add null guard before it:
```js
  if (!$('exec-window')) return;
  $('exec-window').innerHTML = checks.map(c => {
```

Also remove the `renderExecution(raw)` call from the `requestAnimationFrame` in `load()`:

Find:
```js
      renderExecution(raw);
```

Delete that line.

### Step 2: Restructure the `<!-- BOTTOM -->` section in `should-i-trade-v6.html`

Find the entire `<!-- BOTTOM -->` block:
```html
    <!-- BOTTOM -->
    <div class="bottom-row">
      <!-- Sector + Industry Performance -->
      <div class="card">
        <div class="card-title"><span class="icon-label"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>Breadth Under the Surface</span></div>
        <div class="card-subtitle">11 SECTORS</div>
        <div id="sector-bars"></div>
        <div class="card-subtitle">INDUSTRY &amp; STYLE</div>
        <div id="industry-bars"></div>
      </div>

      <!-- Execution Window -->
      <div class="card">
        <div class="card-title"><span class="icon-label"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>Execution Window</span></div>
        <div id="exec-window"></div>
      </div>

      <!-- Scoring Weights + Sparkline -->
      <div class="card">
        <div class="card-title"><span class="icon-label"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>Scoring Weights</span> <button class="btn" style="font-size:9px;padding:2px 6px" onclick="toggleSettings()"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> Edit</button></div>
        <div id="score-weights"></div>
        <div style="border-top:1px solid var(--border);margin-top:10px;padding-top:10px;display:flex;justify-content:space-between;">
          <span id="weight-total-label" style="color:var(--muted);font-size:10px;">OFFICIAL SCORE</span>
          <span style="font-size:16px;font-weight:800;" id="total-score-bottom">—</span>
        </div>
        <div id="weight-scenario-note" style="display:none;margin-top:6px;font-size:9px;color:var(--muted);line-height:1.6;">
          What-if only. The hero decision, alerts, conflicts, history, and roundtable use backend weights.
        </div>
        <div style="margin-top:8px;font-size:9px;color:var(--muted);line-height:1.7;">
          <span style="color:var(--green);">●</span> 85+: RISK-ON (full exposure)<br>
          <span style="color:var(--green);">●</span> 70–84: CONSTRUCTIVE (standard exposure)<br>
          <span style="color:var(--yellow);">●</span> 55–69: SELECTIVE (moderate exposure)<br>
          <span style="color:var(--orange);">●</span> 40–54: DE-RISK (reduced exposure)<br>
          <span style="color:var(--red);">●</span> &lt;40: RISK-OFF (defensive / flat)
        </div>

        <div class="sparkline-wrap">
          <div class="sparkline-label">
            <span>Score history <span id="spark-paused" style="display:none;color:var(--red);margin-left:6px;">⏸ paused — bad data</span></span>
            <span id="spark-range">—</span>
          </div>
          <svg class="sparkline" id="sparkline" viewBox="0 0 400 60" preserveAspectRatio="none"></svg>
          <div class="spark-legend" id="spark-legend" role="group" aria-label="Toggle sparkline series">
            <button class="spark-leg-item" data-key="total" onclick="toggleSparkLine('total',this)" aria-pressed="true"><div class="spark-leg-dot" style="background:#e0e8f0"></div>Total</button>
            <button class="spark-leg-item dimmed" data-key="v" onclick="toggleSparkLine('v',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#00b0ff"></div>Vol</button>
            <button class="spark-leg-item dimmed" data-key="tr" onclick="toggleSparkLine('tr',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#00e676"></div>Trend</button>
            <button class="spark-leg-item dimmed" data-key="br" onclick="toggleSparkLine('br',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#ffd740"></div>Breadth</button>
            <button class="spark-leg-item dimmed" data-key="mo" onclick="toggleSparkLine('mo',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#ff9100"></div>Mom</button>
            <button class="spark-leg-item dimmed" data-key="ma" onclick="toggleSparkLine('ma',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#7c4dff"></div>Macro</button>
          </div>
        </div>
      </div>
    </div>
```

Replace with:
```html
    <!-- BOTTOM -->
    <div class="bottom-row">
      <!-- Sector + Industry Performance -->
      <div class="card">
        <div class="card-title"><span class="icon-label"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>Breadth Under the Surface</span></div>
        <div class="card-subtitle">11 SECTORS</div>
        <div id="sector-bars"></div>
        <div class="card-subtitle">INDUSTRY &amp; STYLE</div>
        <div id="industry-bars"></div>
      </div>

      <!-- Score History Sparkline -->
      <div class="card">
        <div class="card-title"><span class="icon-label"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>Score History</span></div>
        <div class="sparkline-wrap">
          <div class="sparkline-label">
            <span>Last 12 hours <span id="spark-paused" style="display:none;color:var(--red);margin-left:6px;">⏸ paused — bad data</span></span>
            <span id="spark-range">—</span>
          </div>
          <svg class="sparkline" id="sparkline" viewBox="0 0 400 60" preserveAspectRatio="none"></svg>
          <div class="spark-legend" id="spark-legend" role="group" aria-label="Toggle sparkline series">
            <button class="spark-leg-item" data-key="total" onclick="toggleSparkLine('total',this)" aria-pressed="true"><div class="spark-leg-dot" style="background:#dce6f0"></div>Total</button>
            <button class="spark-leg-item dimmed" data-key="v" onclick="toggleSparkLine('v',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#3b82f6"></div>Vol</button>
            <button class="spark-leg-item dimmed" data-key="tr" onclick="toggleSparkLine('tr',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#00e676"></div>Trend</button>
            <button class="spark-leg-item dimmed" data-key="br" onclick="toggleSparkLine('br',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#ffd740"></div>Breadth</button>
            <button class="spark-leg-item dimmed" data-key="mo" onclick="toggleSparkLine('mo',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#ff9100"></div>Mom</button>
            <button class="spark-leg-item dimmed" data-key="ma" onclick="toggleSparkLine('ma',this)" aria-pressed="false"><div class="spark-leg-dot" style="background:#7c4dff"></div>Macro</button>
          </div>
        </div>
      </div>
    </div>
    <!-- Hidden elements kept for JS compatibility -->
    <div id="exec-window" style="display:none" aria-hidden="true"></div>
```

### Step 3: Move scoring weights into the settings drawer in `should-i-trade-v6.html`

In the `<!-- SETTINGS DRAWER -->`, find the settings-section for pillar weights. After the existing `<div class="settings-section">` block (which has the weight sliders), add a new section:

Find the line just before `<div class="settings-section" style="border-top:1px solid var(--border);padding-top:16px;">` (the theme section), and insert before it:

```html
    <div class="settings-section" style="border-top:1px solid var(--border);padding-top:16px;">
      <div class="settings-section-title">Score Weights — What-If View</div>
      <div id="score-weights"></div>
      <div style="border-top:1px solid var(--border);margin-top:10px;padding-top:10px;display:flex;justify-content:space-between;">
        <span id="weight-total-label" style="color:var(--muted);font-size:10px;">OFFICIAL SCORE</span>
        <span style="font-size:16px;font-weight:800;font-family:'Fira Code',monospace;" id="total-score-bottom">—</span>
      </div>
      <div id="weight-scenario-note" style="display:none;margin-top:6px;font-size:10px;color:var(--muted);line-height:1.6;">
        What-if only. The hero decision, alerts, conflicts, history, and roundtable use backend weights.
      </div>
      <div style="margin-top:10px;font-size:10px;color:var(--muted);line-height:1.9;">
        <span style="color:var(--green);">●</span> 85+: RISK-ON — full exposure<br>
        <span style="color:var(--green);">●</span> 70–84: CONSTRUCTIVE — standard exposure<br>
        <span style="color:var(--yellow);">●</span> 55–69: SELECTIVE — moderate exposure<br>
        <span style="color:var(--orange);">●</span> 40–54: DE-RISK — reduced exposure<br>
        <span style="color:var(--red);">●</span> &lt;40: RISK-OFF — defensive / flat
      </div>
    </div>
```

### Step 4: Update `bottom-row` CSS to 2-column grid in `static/app.css`

Find:
```css
  .bottom-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
```

Replace with:
```css
  .bottom-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
```

### Step 5: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 6: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add should-i-trade-v6.html static/app.css static/app.js
git commit -m "feat: remove execution window, standalone sparkline, move weights to settings"
```

---

## Task 8: Accessibility + Reduced-Motion Polish

**Files:**
- Modify: `static/app.css` (focus rings, reduced-motion, minimum touch targets, card `border-radius`)

### Step 1: Add global focus ring and reduced-motion rules to `static/app.css`

After the `* { box-sizing: border-box; margin: 0; padding: 0; }` line, add:
```css
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  }
```

### Step 2: Ensure all `.card` elements use `border-radius: 4px`

Find:
```css
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 18px; }
```

Replace `6px` with `4px`:
```css
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 20px; }
```

### Step 3: Ensure `.btn` focus is visible

Find:
```css
  .btn { background: transparent; border: 1px solid var(--border); color: var(--muted); padding: 4px 10px; cursor: pointer; border-radius: 3px; font-size: 10px; font-family: inherit; letter-spacing: 0.5px; transition: all 0.2s; }
  .btn:hover { border-color: var(--accent); color: var(--accent); }
```

Replace with:
```css
  .btn { background: transparent; border: 1px solid var(--border); color: var(--muted); padding: 4px 10px; cursor: pointer; border-radius: 3px; font-size: 11px; font-family: inherit; letter-spacing: 0.5px; transition: border-color 0.15s, color 0.15s; }
  .btn:hover { border-color: var(--accent); color: var(--accent); }
  .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

### Step 4: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 5: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add static/app.css
git commit -m "style: accessibility — focus rings, reduced-motion, border-radius consistency"
```

---

## Task 9: Responsive Layout — Mobile Pillar Grid

**Files:**
- Modify: `static/app.css` (mobile media query for pillars and bottom-row)

### Step 1: Update the mobile media query in `static/app.css`

The file already has `@media (max-width: 480px)` and `@media (max-width: 768px)` blocks. Find the `@media (max-width: 480px)` block and update/add these rules:

```css
  @media (max-width: 768px) {
    .pillars-row { grid-template-columns: repeat(2, 1fr); }
    .bottom-row  { grid-template-columns: 1fr; }
    .score-strip { flex-wrap: wrap; gap: 12px; }
    .strip-caveat { width: 100%; text-align: left; }
  }

  @media (max-width: 480px) {
    .main { padding: 10px 12px; gap: 10px; }
    .header { padding: 8px 12px; }
    .header-score { display: none; }
    .pillars-row { grid-template-columns: 1fr; }
    .score-strip { padding: 12px 14px; }
    .strip-circle { width: 64px; height: 64px; }
    .strip-circle svg { width: 64px; height: 64px; }
    .score-num .val { font-size: 20px; }
    .decision-badge { font-size: 15px; }
  }
```

Note: Find the existing `@media (max-width: 480px)` block in app.css and replace it with this version (merge with any existing rules you want to keep, but these override the critical layout rules).

### Step 2: Run tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all tests pass

### Step 3: Commit

```bash
cd /Users/nabulizi/should-i-trade
git add static/app.css
git commit -m "style: responsive layout — 2-col pillars tablet, 1-col mobile"
```

---

## Task 10: Final Verification

- [ ] Run all JS tests

```bash
cd /Users/nabulizi/should-i-trade && npm test
```

Expected: all pass

- [ ] Run all Python tests

```bash
cd /Users/nabulizi/should-i-trade && python3 -m unittest discover -v 2>&1 | tail -20
```

Expected: all pass — no Python files were changed

- [ ] Start the app and visually verify key flows

```bash
cd /Users/nabulizi/should-i-trade && python3 server.py &
sleep 8
open http://localhost:8765
```

Check on desktop (1280px):
- Score strip visible above fold
- Pillars are the first major content block
- Roundtable + Watchlist show as collapsed toggles
- Header shows score badge after data loads

Check on mobile (390px wide in browser devtools):
- Pillars stack to 1 column
- Score strip wraps neatly
- Buttons remain tappable

- [ ] Kill the server after testing

```bash
kill $(lsof -ti:8765)
```

- [ ] Push the branch

```bash
cd /Users/nabulizi/should-i-trade && git push origin feature/minimal-calm-ui
```

---

## Self-Review

| Spec Requirement | Task |
|---|---|
| Remove scrolling ticker | Task 2 |
| Simplify header to 3 controls + score badge | Task 3 |
| Replace 3-col hero with compact strip | Task 4 |
| Pillar cards become hero — larger score, wider bar | Task 5 |
| Collapse roundtable + watchlist by default | Task 6 |
| Remove execution window card | Task 7 |
| Move scoring weights to settings drawer | Task 7 |
| Sparkline stays visible (own card) | Task 7 |
| CSS tokens: warmer bg, single accent, single surface | Task 1 |
| Inter for labels, Fira Code for numbers | Tasks 1, 4, 5 |
| Focus rings + reduced-motion | Task 8 |
| Mobile: 2-col tablet / 1-col mobile pillars | Task 9 |
| All existing tests pass | Tasks 1–9 step-by-step + Task 10 |
| No backend changes | ✅ confirmed — only app.css, app.js, html |
