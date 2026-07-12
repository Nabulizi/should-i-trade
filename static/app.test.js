import { beforeEach, describe, it, expect } from 'vitest';
import {
  scoreColor,
  colorClass,
  decisionForScore,
  chgStr,
  FALLBACK_DECISION_BANDS,
  DEFAULT_WEIGHTS,
  buildWeightScenario,
  buildRadarChart,
  validateDashboardPayload,
  isDefaultWeights,
  volTargetLine,
  loadVolTarget,
  reliabilityLine,
  asOfLine,
} from './app.js';

beforeEach(() => {
  localStorage.clear();
});

describe('buildRadarChart', () => {
  it('renders an accessible SVG summary of all five pillar scores', () => {
    const svg = buildRadarChart({
      volatility: { score: 95 },
      trend: { score: 100 },
      breadth: { score: 87 },
      momentum: { score: 75 },
      macro: { score: 73 },
    });

    expect(svg).toContain('role="img"');
    expect(svg).toContain('VOL 95, TREND 100, BREADTH 87, MOM 75, MACRO 73');
    expect(svg).toContain('<polygon');
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

  it('renders exposure, target, realized vol, horizon, and the not-personalized note', () => {
    const html = volTargetLine(vt);
    expect(html).toContain('~72% SPY-equivalent exposure');
    expect(html).toContain('7.8% annual-vol target');
    expect(html).toContain('20d realized vol 10.8% annualized');
    expect(html).toContain('not personalized');
    expect(html).toContain('vol-target-line');
  });

  it('recomputes exposure from a user-selected target (what-if)', () => {
    const html = volTargetLine(vt, 15);
    // 15 / 10.8 = 138.9% → capped at 100%
    expect(html).toContain('~100% SPY-equivalent exposure');
    expect(html).toContain('15% annual-vol target (your setting)');
  });

  it('user target of 5% halves the default-target exposure', () => {
    const html = volTargetLine(vt, 5);
    // 5 / 10.8 = 46.3%
    expect(html).toContain('~46% SPY-equivalent exposure');
  });

  it('falls back to daily-vol copy for legacy payloads without annual fields', () => {
    const html = volTargetLine({ exposure_pct: 72.4, realized_vol_pct: 0.7 });
    expect(html).toContain('~72% SPY-equivalent exposure');
    expect(html).toContain('daily vol 0.7%');
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

describe('reliabilityLine (P1-001/P1-002)', () => {
  it('renders the backend reliability level and coverage', () => {
    const html = reliabilityLine({ level: 'high', coverage_pct: 100, critical_ok: true });
    expect(html).toContain('Reliability');
    expect(html).toContain('High');
    expect(html).toContain('100% coverage');
  });

  it('is independent of score direction — level comes only from the payload', () => {
    // A low-score day with clean data must still render as high reliability.
    const html = reliabilityLine({ level: 'high', coverage_pct: 97.3 });
    expect(html).toContain('High');
    expect(html).toContain('green');
  });

  it('renders none as data unavailable', () => {
    expect(reliabilityLine({ level: 'none', coverage_pct: 0 })).toContain('Data unavailable');
  });

  it('returns empty string for missing payload', () => {
    expect(reliabilityLine(null)).toBe('');
    expect(reliabilityLine({})).toBe('');
  });
});

describe('asOfLine (P1-004/P1-005)', () => {
  it('frames weekend readings as based on the last close, planning only', () => {
    const html = asOfLine({ session: 'weekend', market_data_as_of: '2026-07-10', calculated_at: '2026-07-11T23:22:00-04:00' });
    expect(html).toContain('Market closed (weekend)');
    expect(html).toContain('2026-07-10');
    expect(html).toContain('planning context only');
  });

  it('is empty during regular hours', () => {
    expect(asOfLine({ session: 'open', market_data_as_of: '2026-07-10' })).toBe('');
  });

  it('labels premarket without the planning-only note', () => {
    const html = asOfLine({ session: 'premarket', market_data_as_of: '2026-07-09' });
    expect(html).toContain('Premarket');
    expect(html).not.toContain('planning context only');
  });

  it('falls back to the last history bar date and empty when no date is known', () => {
    expect(asOfLine({ session: 'weekend', history_last_bar: '2026-07-10' })).toContain('2026-07-10');
    expect(asOfLine({ session: 'weekend' })).toBe('');
    expect(asOfLine(null)).toBe('');
  });
});
