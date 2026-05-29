import { describe, it, expect } from 'vitest';
import {
  scoreColor,
  colorClass,
  decisionForScore,
  chgStr,
  FALLBACK_DECISION_BANDS,
} from './app.js';

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
    expect(decisionForScore(90).position_size).toBe('FULL EXPOSURE');
    expect(decisionForScore(72).position_size).toBe('STANDARD EXPOSURE');
    expect(decisionForScore(60).position_size).toBe('MODERATE EXPOSURE');
    expect(decisionForScore(45).position_size).toBe('REDUCED EXPOSURE');
    expect(decisionForScore(10).position_size).toBe('DEFENSIVE / FLAT');
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
