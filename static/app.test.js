import { beforeEach, describe, it, expect } from 'vitest';
import {
  scoreColor,
  colorClass,
  decisionForScore,
  chgStr,
  FALLBACK_DECISION_BANDS,
  DEFAULT_WEIGHTS,
  buildWeightScenario,
  buildPillarBars,
  validateDashboardPayload,
  isDefaultWeights,
  volTargetLine,
  loadVolTarget,
  roundtableProvenance,
  reliabilityLine,
  asOfLine,
  buildLiquidityChips,
  liquidityVotesLine,
  liquidityLongerLine,
  liquidityNoteHtml,
  fedPathLine,
  riskLineHtml,
  threeQuestionsHtml,
  todaysReadHtml,
  hygHintHtml,
  onHintClick,
  onHintKey,
} from './app.js';

beforeEach(() => {
  localStorage.clear();
});

describe('riskLineHtml', () => {
  const checks = [
    { label: 'SPY volatility', on: false, detail: '11.6%, below the 13.2% median' },
    { label: 'SPY trend', on: true, detail: 'Below its 50-day average' },
    { label: 'Credit', on: true, detail: 'HYG below its 50-day average' },
  ];
  const read = (level, list = checks, extra = {}) => ({
    data_quality: { valid: true }, risk_read: { level, color: 'orange', flags: [], checks: list }, ...extra,
  });

  it('leads with the level and shows every check, on or off, in words', () => {
    const html = riskLineHtml(read('Elevated'));
    expect(html).toContain('Elevated');
    expect(html).toContain('Below its 50-day average');
    expect(html).toContain('11.6%, below the 13.2% median');
    expect((html.match(/risk-check-state">OK/g) || []).length).toBe(1);
    expect((html.match(/risk-check-state">Warning/g) || []).length).toBe(2);
    expect(html).not.toMatch(/>(On|Off)</);
  });

  it('counts the warnings and says how the count sets the level', () => {
    const html = riskLineHtml(read('Elevated'));
    expect(html).toContain('2 of 3 warning');
    expect(html).toContain('0 warnings: Normal');
    expect(html).toContain('1–2: Elevated');
    expect(html).toContain('3: High');
  });

  it('explains HYG on the credit check only', () => {
    const html = riskLineHtml(read('Elevated'));
    expect((html.match(/hint-btn/g) || []).length).toBe(1);
    expect(html.indexOf('hint-btn')).toBeGreaterThan(html.indexOf('>Credit<'));
  });

  it('says plainly when no check is on', () => {
    const off = checks.map(c => ({ ...c, on: false }));
    const html = riskLineHtml(read('Normal', off));
    expect(html).toContain('0 of 3 warning');
    expect(html).not.toContain('risk-check-state">Warning');
  });

  it('marks the current step on the scale in a way a screen reader gets', () => {
    const html = riskLineHtml(read('Elevated'));
    expect(html).toContain('aria-label="Risk level Elevated, second of three"');
    expect((html.match(/risk-step current/g) || []).length).toBe(1);
  });

  it('labels the history as exploratory, not a forecast', () => {
    const html = riskLineHtml(read('High'));
    for (const text of ['10%', '22%', '41%', 'not a forecast']) expect(html).toContain(text);
  });

  it('shows the score with its pillars beside the level', () => {
    const html = riskLineHtml(read('Elevated', checks, {
      total_score: 32, decision: 'RISK-OFF',
      pillars: { trend: { score: 12, details: { x: 1 }, reasons: [] } },
    }));
    for (const text of ['>32<', 'RISK-OFF', 'Trend']) expect(html).toContain(text);
  });

  it('keeps coverage, basis and the disclaimer visible as one line of fine print', () => {
    const html = riskLineHtml(read('Elevated', checks, {
      timestamp: '20:32 ET', reliability: { coverage_pct: 100 },
      as_of: { session: 'weekend', market_data_as_of: '2026-10-30' },
    }));
    const foot = html.slice(html.indexOf('risk-foot'));
    for (const text of ['100%', '20:32 ET', '2026-10-30', 'return-timing edge']) expect(foot).toContain(text);
  });

  it('never shows a level or score when data is invalid or missing', () => {
    const invalid = riskLineHtml({ data_quality: { valid: false }, total_score: 32, risk_read: { level: 'Normal', checks } });
    expect(invalid).toContain('Data unavailable');
    expect(invalid).not.toContain('Normal');
    expect(invalid).not.toContain('>32<');
    expect(riskLineHtml({ data_quality: { valid: true }, risk_read: { level: null, checks: [] } })).toContain('Not enough data');
    expect(riskLineHtml({ data_quality: { valid: true } })).toContain('Not enough data');
  });

  it('escapes backend strings', () => {
    const html = riskLineHtml(read('Elevated', [{ label: '<img>', on: true, detail: '<b>' }]));
    expect(html).not.toContain('<img>');
    expect(html).not.toContain('<b>');
  });
});

describe('hygHintHtml', () => {
  it('states the inverse relationship both ways, with a text alternative to the arrows', () => {
    const html = hygHintHtml();
    expect(html).toContain('HYG price up ↑ = junk bond yields down ↓');
    expect(html).toContain('HYG price down ↓ = junk bond yields up ↑');
    expect(html).toContain('high-yield');
    expect(html).toContain('aria-label="What HYG means"');
  });

  it('does not present HYG as a pure credit measure', () => {
    expect(hygHintHtml()).toContain('Treasury yields');
  });
});

describe('hint open and close', () => {
  const mount = () => {
    document.body.innerHTML = `<div id="outside"></div><div id="a">${hygHintHtml()}</div><div id="b">${hygHintHtml()}</div>`;
    return [...document.querySelectorAll('.hint-btn')];
  };
  const click = el => onHintClick({ target: el });

  it('opens on tap and reflects that for screen readers', () => {
    const [btn] = mount();
    click(btn);
    expect(btn.closest('.hint').classList.contains('open')).toBe(true);
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });

  it('closes on a second tap', () => {
    const [btn] = mount();
    click(btn);
    click(btn);
    expect(btn.closest('.hint').classList.contains('open')).toBe(false);
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  it('only keeps one open at a time', () => {
    const [first, second] = mount();
    click(first);
    click(second);
    expect(first.closest('.hint').classList.contains('open')).toBe(false);
    expect(second.closest('.hint').classList.contains('open')).toBe(true);
  });

  it('closes on an outside tap', () => {
    const [btn] = mount();
    click(btn);
    click(document.getElementById('outside'));
    expect(btn.closest('.hint').classList.contains('open')).toBe(false);
  });

  it('stays open when tapping inside the explanation', () => {
    const [btn] = mount();
    click(btn);
    click(btn.closest('.hint').querySelector('.hint-panel'));
    expect(btn.closest('.hint').classList.contains('open')).toBe(true);
  });

  it('closes on Escape, and ignores other keys', () => {
    const [btn] = mount();
    click(btn);
    onHintKey({ key: 'a' });
    expect(btn.closest('.hint').classList.contains('open')).toBe(true);
    onHintKey({ key: 'Escape' });
    expect(btn.closest('.hint').classList.contains('open')).toBe(false);
  });
});

describe('todaysReadHtml', () => {
  const event = { name: 'Jobs Report', date_pretty: 'Nov 06', urgency: '6d' };

  it('is never empty when there is no history and nothing disagrees', () => {
    const html = todaysReadHtml({ conflicts: [], econ_events: [event] });
    expect(html).toContain('No previous close saved yet');
    expect(html).toContain('No signal conflicts flagged');
    expect(html).toContain('Jobs Report');
    expect(html).toContain('Nov 06');
  });

  it('leaves those lines out when the strip and conflict cards are showing them', () => {
    const html = todaysReadHtml({
      yesterday: { pillars: {} }, conflicts: [{ title: 'x' }], econ_events: [],
    });
    expect(html).not.toContain('No previous close');
    expect(html).not.toContain('No signal conflicts');
  });

  it('says so when the calendar has nothing upcoming', () => {
    expect(todaysReadHtml({ conflicts: [], econ_events: [] })).toContain('No release dates listed');
  });

  it('escapes backend strings', () => {
    expect(todaysReadHtml({ conflicts: [], econ_events: [{ name: '<img>', date_pretty: 'x' }] })).not.toContain('<img>');
  });
});

describe('threeQuestionsHtml', () => {
  const dash = {
    vol_target: { exposure_pct: 67, realized_annual_vol_pct: 11.6, target_annual_vol_pct: 7.8 },
    futures_tape: { items: [
      { symbol: 'ES', change_pct: -1.81, available: true },
      { symbol: 'NQ', change_pct: -3.48, available: true },
      { symbol: 'RTY', change_pct: -1.6, available: true },
    ] },
    pillars: {
      volatility: { details: { vix_level: 19.42, vix_label: 'Elevated', vix_trend: 'Spiking' } },
      trend: { details: { above_50: false, above_200: true } },
      breadth: { details: { sectors_positive: 6, sectors_total: 11 } },
      momentum: { details: { rs_rotation_label: 'Defensive Rotation' } },
      macro: { details: { hyg_label: 'Below 50d' } },
    },
    liquidity: {
      tone: 'Neutral', longer: { tone: 'Tightening' },
      items: [{ key: 'hy_spread', value: 3.26, level: 'Calm' }],
      fed_path: { spread: 0.73, lean: 'leans hikes' },
    },
  };

  it('asks the three questions and answers from the payload', () => {
    const html = threeQuestionsHtml(dash);
    for (const text of ['How rough?', 'How healthy?', "What's the backdrop?", '19.42', 'Spiking', '11.6%',
      'Below 50-day', 'above 200-day', '6 of 11', 'Defensive Rotation', '3.26', 'Calm',
      'Below 50d', 'Leans hikes', 'Flat 4w, tighter 13w', '67%, illustrative', 'ES -1.81%, NQ -3.48%']) {
      expect(html).toContain(text);
    }
  });

  it('gives every question the same number of rows when data is complete', () => {
    const cards = threeQuestionsHtml(dash).split('question-card').slice(1);
    expect(cards.map(card => (card.match(/question-row/g) || []).length)).toEqual([4, 4, 4]);
  });

  it('shows no figures beside a data-unavailable headline', () => {
    const html = threeQuestionsHtml({ ...dash, data_quality: { valid: false } });
    expect(html).not.toContain('19.42');
    expect(html).not.toContain('3.26');
    expect((html.match(/No data/g) || []).length).toBe(3);
  });

  it('explains HYG beside its row', () => {
    const html = threeQuestionsHtml(dash);
    expect((html.match(/hint-btn/g) || []).length).toBe(1);
    expect(html).toContain('HYG price up');
  });

  it('leaves out futures it has no reading for', () => {
    const html = threeQuestionsHtml({ ...dash, futures_tape: { items: [{ symbol: 'ES', change_pct: null, available: false }] } });
    expect(html).not.toContain('Futures');
  });

  it('shows no data rather than undefined when inputs are missing', () => {
    const html = threeQuestionsHtml({ pillars: {} });
    expect(html).not.toContain('undefined');
    expect(html).not.toContain('NaN');
    expect(html).toContain('No data');
  });

  it('does not claim a trend side it does not know', () => {
    const html = threeQuestionsHtml({ pillars: { trend: { details: {} } } });
    expect(html).not.toContain('50-day');
  });

  it('shows the Tightening with high volatility flag when it applies', () => {
    const html = threeQuestionsHtml({ ...dash, liquidity: { ...dash.liquidity, high_vol_tightening: true, high_vol_note: 'Both are on' } });
    expect(html).toContain('Both are on');
  });
});

describe('buildLiquidityChips', () => {
  const item = {
    key: 'hy_spread', label: 'HY spread (%)', value: 3.26, change: -0.2,
    direction: 'loosening', as_of: '2026-10-29', available: true,
    hint: 'Below ~4 calm', source: 'FRED BAMLH0A0HYM2',
  };

  it('states the direction in words with the level and signed change', () => {
    const html = buildLiquidityChips([item]);
    expect(html).toContain('Loosening');
    expect(html).toContain('3.26');
    expect(html).toContain('-0.20');
    expect(html).toContain('Oct 29');
  });

  it('shows a failed series as no data, never as a direction', () => {
    const html = buildLiquidityChips([{ ...item, available: false, value: null, change: null, direction: null, as_of: null }]);
    expect(html).toContain('No data');
    expect(html).not.toContain('Loosening');
    expect(html).not.toContain('null');
  });

  it('escapes backend strings', () => {
    expect(buildLiquidityChips([{ ...item, label: '<img>' }])).not.toContain('<img>');
  });

  it('puts the spread level tag on screen, not just in a tooltip', () => {
    const html = buildLiquidityChips([{ ...item, level: 'Elevated', hint: '' }]);
    expect(html).toContain('>Elevated<');
  });

  it('counts votes so a Neutral headline does not sit beside a lopsided count', () => {
    expect(liquidityVotesLine({ valid: true, loosening_votes: 1, tightening_votes: 0 })).toBe('Votes: 1 looser · 0 tighter');
    expect(liquidityVotesLine({ valid: false })).toBe('No read');
  });

  it('does not paint a loosening series as a positive signal', () => {
    expect(buildLiquidityChips([item])).not.toContain('future-chg up');
  });

  it('shows the longer reading beside the 4-week one', () => {
    expect(liquidityLongerLine({ longer: { lookback_weeks: 13, tone: 'Tightening' } })).toBe('13 weeks: Tightening');
    expect(liquidityLongerLine({ longer: { lookback_weeks: 13, tone: 'Unavailable' } })).toBe('13 weeks: no read');
    expect(liquidityLongerLine({})).toBe('');
  });

  it('shows the Tightening plus high volatility flag only when it applies', () => {
    expect(liquidityNoteHtml({ high_vol_tightening: true, high_vol_note: '<b>39%</b>' })).toContain('&lt;b&gt;39%');
    expect(liquidityNoteHtml({ high_vol_tightening: false, high_vol_note: 'x' })).toBe('');
  });

  it('shows the 2Y vs Fed funds gap with a sign, or nothing without data', () => {
    expect(fedPathLine({ fed_path: { spread: 0.98, lean: 'leans hikes' } })).toBe('2Y vs Fed funds: +0.98, leans hikes');
    expect(fedPathLine({ fed_path: { spread: -0.3, lean: 'leans cuts' } })).toBe('2Y vs Fed funds: -0.30, leans cuts');
    expect(fedPathLine({ fed_path: null })).toBe('');
  });

  it('reports when there are no items at all', () => {
    expect(buildLiquidityChips([])).toContain('unavailable');
  });
});

describe('buildPillarBars (P1-014/P1-015)', () => {
  const pillars = {
    volatility: { score: 95, details: { vix_level: 15 }, reasons: ['+35 VIX'] },
    trend: { score: 100, details: { regime: 'Uptrend' }, reasons: ['+25 SPY > 20d'] },
    breadth: { score: 87, details: { rsp_price: 1 }, reasons: ['+35 Sectors'] },
    momentum: { score: 75, details: { rsp_vs_spy: 0.1 }, reasons: ['+20 RSP'] },
    macro: { score: 73, details: { tnx_value: 4 }, reasons: ['+15 10Y'] },
  };

  it('renders one accessible bar per pillar with its score', () => {
    const html = buildPillarBars(pillars);
    expect(html).toContain('Volatility');
    expect(html).toContain('pillar 95 of 100');
    expect(html).toContain('width:100%');
    expect((html.match(/hero-pillar-row/g) || []).length).toBe(5);
    expect(html).not.toContain('<polygon');    // the radar is gone (P1-014)
  });

  it('marks a neutral-fallback pillar as no data, not as a score', () => {
    const withMissing = { ...pillars,
      macro: { score: 50, details: {}, reasons: ['⚠ Macro data unavailable — neutral 50'] } };
    const html = buildPillarBars(withMissing);
    expect(html).toContain('missing');
    expect(html).toContain('no data');
  });
});

describe('validateDashboardPayload', () => {
  const validPayload = {
    total_score: 72,
    decision: 'CONSTRUCTIVE',
    position_size: 'STANDARD EXPOSURE',
    pillars: Object.fromEntries(
      ['volatility', 'trend', 'breadth', 'momentum', 'macro'].map(key => [key, { score: 72, details: {} }])
    ),
  };

  it('accepts a complete dashboard payload', () => {
    expect(validateDashboardPayload(validPayload)).toBe(true);
  });

  it('rejects missing and malformed pillar data', () => {
    expect(validateDashboardPayload({})).toBe(false);
    expect(validateDashboardPayload({ ...validPayload, pillars: {} })).toBe(false);
    expect(validateDashboardPayload({ ...validPayload, total_score: 'not-a-score' })).toBe(false);
  });
});

// ── scoreColor ────────────────────────────────────────────────────────────
describe('scoreColor', () => {
  it('returns green for scores >= 70', () => {
    expect(scoreColor(70)).toBe('var(--green)');
    expect(scoreColor(90)).toBe('var(--green)');
    expect(scoreColor(100)).toBe('var(--green)');
  });

  it('returns yellow for scores 55–69', () => {
    expect(scoreColor(55)).toBe('var(--yellow)');
    expect(scoreColor(60)).toBe('var(--yellow)');
    expect(scoreColor(69)).toBe('var(--yellow)');
  });

  it('returns orange for scores 40–54', () => {
    expect(scoreColor(40)).toBe('var(--orange)');
    expect(scoreColor(54)).toBe('var(--orange)');
  });

  it('returns red for scores below 40', () => {
    expect(scoreColor(0)).toBe('var(--red)');
    expect(scoreColor(20)).toBe('var(--red)');
    expect(scoreColor(39)).toBe('var(--red)');
  });
});

// ── colorClass ────────────────────────────────────────────────────────────
describe('colorClass', () => {
  it('returns c-green for scores >= 70', () => {
    expect(colorClass(70)).toBe('c-green');
    expect(colorClass(100)).toBe('c-green');
  });

  it('returns c-yellow for scores 55–69', () => {
    expect(colorClass(55)).toBe('c-yellow');
    expect(colorClass(69)).toBe('c-yellow');
  });

  it('returns c-orange for scores 40–54', () => {
    expect(colorClass(40)).toBe('c-orange');
    expect(colorClass(54)).toBe('c-orange');
  });

  it('returns c-red for scores below 40', () => {
    expect(colorClass(0)).toBe('c-red');
    expect(colorClass(39)).toBe('c-red');
  });
});

// ── decisionForScore ──────────────────────────────────────────────────────
describe('decisionForScore', () => {
  it('returns RISK-ON for 85+', () => {
    expect(decisionForScore(85).decision).toBe('RISK-ON');
    expect(decisionForScore(100).decision).toBe('RISK-ON');
  });

  it('returns CONSTRUCTIVE for 70–84', () => {
    expect(decisionForScore(70).decision).toBe('CONSTRUCTIVE');
    expect(decisionForScore(84).decision).toBe('CONSTRUCTIVE');
  });

  it('returns SELECTIVE for 55–69', () => {
    expect(decisionForScore(55).decision).toBe('SELECTIVE');
    expect(decisionForScore(69).decision).toBe('SELECTIVE');
  });

  it('returns DE-RISK for 40–54', () => {
    expect(decisionForScore(40).decision).toBe('DE-RISK');
    expect(decisionForScore(54).decision).toBe('DE-RISK');
  });

  it('returns RISK-OFF for below 40', () => {
    expect(decisionForScore(0).decision).toBe('RISK-OFF');
    expect(decisionForScore(39).decision).toBe('RISK-OFF');
  });

  it('returns position_size in the result', () => {
    expect(decisionForScore(90).position_size).toBe('STRONGEST CONDITIONS');
    expect(decisionForScore(72).position_size).toBe('CONSTRUCTIVE CONDITIONS');
    expect(decisionForScore(60).position_size).toBe('MIXED CONDITIONS');
    expect(decisionForScore(45).position_size).toBe('WEAK CONDITIONS');
    expect(decisionForScore(10).position_size).toBe('STRESSED CONDITIONS');
  });

  it('boundary: score 85 is RISK-ON, score 84 is CONSTRUCTIVE', () => {
    expect(decisionForScore(85).decision).toBe('RISK-ON');
    expect(decisionForScore(84).decision).toBe('CONSTRUCTIVE');
  });

  it('uses custom bands when provided', () => {
    const custom = [
      { min: 50, decision: 'BUY',  color: 'green', position: 'full' },
      { min: 0,  decision: 'SELL', color: 'red',   position: 'none' },
    ];
    expect(decisionForScore(60, custom).decision).toBe('BUY');
    expect(decisionForScore(30, custom).decision).toBe('SELL');
    expect(decisionForScore(60, custom).decision_color).toBe('green');
    expect(decisionForScore(60, custom).position_size).toBe('full');
  });
});

// ── chgStr ────────────────────────────────────────────────────────────────
describe('chgStr', () => {
  it('formats positive change with + prefix', () => {
    expect(chgStr(1.5)).toBe('+1.50%');
    expect(chgStr(10)).toBe('+10.00%');
  });

  it('formats negative change without extra prefix', () => {
    expect(chgStr(-2.3)).toBe('-2.30%');
  });

  it('formats zero as +0.00%', () => {
    expect(chgStr(0)).toBe('+0.00%');
  });
});

// ── FALLBACK_DECISION_BANDS ───────────────────────────────────────────────
describe('FALLBACK_DECISION_BANDS', () => {
  it('is an array of 5 bands', () => {
    expect(Array.isArray(FALLBACK_DECISION_BANDS)).toBe(true);
    expect(FALLBACK_DECISION_BANDS.length).toBe(5);
  });

  it('contains expected decision labels', () => {
    const decisions = FALLBACK_DECISION_BANDS.map(b => b.decision);
    expect(decisions).toContain('RISK-ON');
    expect(decisions).toContain('CONSTRUCTIVE');
    expect(decisions).toContain('SELECTIVE');
    expect(decisions).toContain('DE-RISK');
    expect(decisions).toContain('RISK-OFF');
  });

  it('each band has required fields', () => {
    FALLBACK_DECISION_BANDS.forEach(band => {
      expect(band).toHaveProperty('min');
      expect(band).toHaveProperty('decision');
      expect(band).toHaveProperty('color');
      expect(band).toHaveProperty('position');
    });
  });
});

// ── custom weight scenarios ──────────────────────────────────────────────
describe('custom weight scenarios', () => {
  const dashboard = {
    total_score: 65,
    decision: 'SELECTIVE',
    decision_color: 'yellow',
    position_size: 'MODERATE EXPOSURE',
    safety_max_score: null,
    data_quality: { valid: true },
    decision_bands: FALLBACK_DECISION_BANDS,
    pillars: {
      volatility: { score: 20 },
      trend: { score: 90 },
      breadth: { score: 80 },
      momentum: { score: 75 },
      macro: { score: 10 },
    },
  };

  it('recognizes default weights', () => {
    expect(isDefaultWeights(DEFAULT_WEIGHTS)).toBe(true);
    expect(isDefaultWeights({ ...DEFAULT_WEIGHTS, macro: 15 })).toBe(false);
  });

  it('builds a what-if scenario without mutating the official dashboard payload', () => {
    localStorage.setItem('pillarWeights', JSON.stringify({
      volatility: 50,
      trend: 10,
      breadth: 20,
      momentum: 10,
      macro: 10,
    }));

    const scenario = buildWeightScenario(dashboard);

    expect(scenario._customWeights).toBe(true);
    expect(scenario.total_score).not.toBe(dashboard.total_score);
    expect(dashboard.total_score).toBe(65);
    expect(dashboard.decision).toBe('SELECTIVE');
  });

  it('keeps data-unavailable scenarios pinned to the official no-trade payload', () => {
    localStorage.setItem('pillarWeights', JSON.stringify({ ...DEFAULT_WEIGHTS, volatility: 50 }));
    const unavailable = {
      ...dashboard,
      total_score: 0,
      decision: 'DATA UNAVAILABLE',
      data_quality: { valid: false },
    };

    const scenario = buildWeightScenario(unavailable);

    expect(scenario.total_score).toBe(0);
    expect(scenario.decision).toBe('DATA UNAVAILABLE');
    expect(scenario._customWeights).toBe(true);
  });
});

// ── volTargetLine ─────────────────────────────────────────────────────────
describe('volTargetLine (P1-007..009)', () => {
  const vt = {
    exposure_pct: 72.4, realized_vol_pct: 0.68,
    realized_annual_vol_pct: 10.8, target_annual_vol_pct: 7.8, window_days: 20,
  };

  it('shows a plain SPY/cash split on screen with the full method in the tooltip', () => {
    const html = volTargetLine(vt);
    // 72.4 rounds to 72% SPY, complement is 28% cash — always sums to 100.
    expect(html).toContain('Illustrative split: 72% SPY / 28% cash');
    expect(html).toContain('to hold steady risk');
    // Full disclosure (realized vol, horizon, not-personalized) lives in title=
    expect(html).toContain('10.8% annualized');
    expect(html).toContain('not personalized advice');
    expect(html).toContain('vol-target-line');
  });

  it('recomputes exposure from a user-selected target (what-if)', () => {
    const html = volTargetLine(vt, 15);
    // 15 / 10.8 = 138.9% → capped at 100%, cash complement 0%
    expect(html).toContain('100% SPY / 0% cash');
    expect(html).toContain('your setting');
  });

  it('user target of 5% halves the default-target exposure', () => {
    const html = volTargetLine(vt, 5);
    // 5 / 10.8 = 46.3% → 46% SPY, 54% cash
    expect(html).toContain('46% SPY / 54% cash');
  });

  it('SPY% and cash% always sum to exactly 100', () => {
    for (const pct of [0, 1, 33.3, 46.5, 53.5, 99.9, 100]) {
      const html = volTargetLine({ ...vt, exposure_pct: pct });
      const m = html.match(/(\d+)% SPY \/ (\d+)% cash/);
      expect(Number(m[1]) + Number(m[2])).toBe(100);
    }
  });

  it('renders legacy payloads without annual fields', () => {
    const html = volTargetLine({ exposure_pct: 72.4, realized_vol_pct: 0.7 });
    expect(html).toContain('72% SPY / 28% cash');
  });

  it('returns an empty string for null, undefined, or malformed input', () => {
    expect(volTargetLine(null)).toBe('');
    expect(volTargetLine(undefined)).toBe('');
    expect(volTargetLine({})).toBe('');
  });
});

describe('loadVolTarget (P1-009)', () => {
  it('returns null when nothing stored (backend default)', () => {
    expect(loadVolTarget()).toBe(null);
  });

  it('returns a stored preset and rejects out-of-bounds values', () => {
    localStorage.setItem('volTargetAnnual', '10');
    expect(loadVolTarget()).toBe(10);
    localStorage.setItem('volTargetAnnual', '99');
    expect(loadVolTarget()).toBe(null);
  });
});

// ── renderYesterdayStrip ──────────────────────────────────────────────────
import { renderYesterdayStrip } from './app.js';

describe('renderYesterdayStrip', () => {
  const d = {
    total_score: 72, decision: 'CONSTRUCTIVE',
    pillars: {
      volatility: { score: 88 }, trend: { score: 72 }, breadth: { score: 88 },
      momentum: { score: 50 }, macro: { score: 61 },
    },
    yesterday: {
      date: '2026-07-03', total: 68, decision: 'SELECTIVE',
      pillars: { volatility: 88, trend: 69, breadth: 82, momentum: 52, macro: 61 },
    },
  };

  it('renders total delta, pillar deltas, and band transition', () => {
    const html = renderYesterdayStrip(d);
    expect(html).toContain('+4');
    expect(html).toContain('SELECTIVE');
    expect(html).toContain('CONSTRUCTIVE');
    expect(html).toContain('Trend');
    expect(html).toContain('2026-07-03');
  });

  it('returns empty string when no yesterday snapshot', () => {
    expect(renderYesterdayStrip({ ...d, yesterday: null })).toBe('');
  });

  it('omits the transition when the band is unchanged', () => {
    const same = { ...d, yesterday: { ...d.yesterday, decision: 'CONSTRUCTIVE' } };
    expect(renderYesterdayStrip(same)).not.toContain('→');
  });
});

describe('reliabilityLine — data coverage only', () => {
  it('renders coverage as a plain percentage', () => {
    const html = reliabilityLine({ coverage_pct: 100 });
    expect(html).toContain('Data');
    expect(html).toContain('100% coverage');
    expect(html).not.toContain('Reliability');   // renamed per user feedback
  });

  it('is independent of score — a low-score day with complete data still reads 100%', () => {
    const html = reliabilityLine({ coverage_pct: 100, level: 'low', boundary_distance: 1 });
    expect(html).toContain('100% coverage');
    expect(html).toContain('green');
  });

  it('rounds and colors partial coverage', () => {
    const html = reliabilityLine({ coverage_pct: 97.3 });
    expect(html).toContain('97% coverage');
    expect(html).toContain('yellow');
  });

  it('returns empty string for missing payload', () => {
    expect(reliabilityLine(null)).toBe('');
    expect(reliabilityLine({})).toBe('');
  });
});

describe('asOfLine (P1-004/P1-005)', () => {
  it('frames weekend readings as based on the last close, planning only', () => {
    const html = asOfLine({ session: 'weekend', market_data_as_of: '2026-07-10', calculated_at: '2026-07-11T23:22:00-04:00' });
    expect(html).toContain('Based on 2026-07-10 regular-session close');
    expect(html).toContain('planning context only');
    // The header badge already names the session — no duplicate label here.
    expect(html).not.toContain('weekend');
  });

  it('is empty during regular hours', () => {
    expect(asOfLine({ session: 'open', market_data_as_of: '2026-07-10' })).toBe('');
  });

  it('premarket shows the reference close without the planning-only note', () => {
    const html = asOfLine({ session: 'premarket', market_data_as_of: '2026-07-09' });
    expect(html).toContain('Based on 2026-07-09');
    expect(html).not.toContain('planning context only');
  });

  it('falls back to the last history bar date and empty when no date is known', () => {
    expect(asOfLine({ session: 'weekend', history_last_bar: '2026-07-10' })).toContain('2026-07-10');
    expect(asOfLine({ session: 'weekend' })).toBe('');
    expect(asOfLine(null)).toBe('');
  });
});

describe('roundtableProvenance (P1-024)', () => {
  it('shows engine, model, time, and the shared-input note for AI reads', () => {
    const html = roundtableProvenance({
      engine: 'gemini', model: 'models/gemini-2.5-flash',
      generated_at: '2026-07-12T14:00:00Z',
      note: '5 AI lenses over one shared data snapshot — not independent analysts; agreement is overlap, not confirmation.',
    });
    expect(html).toContain('AI · models/gemini-2.5-flash');
    expect(html).toContain('2026-07-12T14:00:00Z');
    expect(html).toContain('not independent analysts');
  });

  it('labels rule-based reads as deterministic', () => {
    const html = roundtableProvenance({ engine: 'rule-based', generated_at: '2026-07-12T14:00:00Z' });
    expect(html).toContain('Rule-based (deterministic)');
  });

  it('returns empty string for legacy payloads without provenance', () => {
    expect(roundtableProvenance({})).toBe('');
    expect(roundtableProvenance(null)).toBe('');
  });
});
