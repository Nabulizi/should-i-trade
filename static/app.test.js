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
  it('returns green for scores >= 80', () => {
    expect(scoreColor(80)).toBe('var(--green)');
    expect(scoreColor(90)).toBe('var(--green)');
    expect(scoreColor(100)).toBe('var(--green)');
  });

  it('returns yellow for scores 60–79', () => {
    expect(scoreColor(60)).toBe('var(--yellow)');
    expect(scoreColor(75)).toBe('var(--yellow)');
    expect(scoreColor(79)).toBe('var(--yellow)');
  });

  it('returns orange for scores 40–59', () => {
    expect(scoreColor(40)).toBe('var(--orange)');
    expect(scoreColor(55)).toBe('var(--orange)');
    expect(scoreColor(59)).toBe('var(--orange)');
  });

  it('returns red for scores below 40', () => {
    expect(scoreColor(0)).toBe('var(--red)');
    expect(scoreColor(20)).toBe('var(--red)');
    expect(scoreColor(39)).toBe('var(--red)');
  });
});

// ── colorClass ────────────────────────────────────────────────────────────
describe('colorClass', () => {
  it('returns c-green for scores >= 80', () => {
    expect(colorClass(80)).toBe('c-green');
    expect(colorClass(100)).toBe('c-green');
  });

  it('returns c-yellow for scores 60–79', () => {
    expect(colorClass(60)).toBe('c-yellow');
    expect(colorClass(79)).toBe('c-yellow');
  });

  it('returns c-orange for scores 40–59', () => {
    expect(colorClass(40)).toBe('c-orange');
  });

  it('returns c-red for scores below 40', () => {
    expect(colorClass(0)).toBe('c-red');
    expect(colorClass(39)).toBe('c-red');
  });
});

// ── decisionForScore ──────────────────────────────────────────────────────
describe('decisionForScore', () => {
  it('returns STRONG YES for 85+', () => {
    expect(decisionForScore(85).decision).toBe('STRONG YES');
    expect(decisionForScore(100).decision).toBe('STRONG YES');
  });

  it('returns YES for 70–84', () => {
    expect(decisionForScore(70).decision).toBe('YES');
    expect(decisionForScore(84).decision).toBe('YES');
  });

  it('returns CAUTION for 55–69', () => {
    expect(decisionForScore(55).decision).toBe('CAUTION');
    expect(decisionForScore(69).decision).toBe('CAUTION');
  });

  it('returns NO for 40–54', () => {
    expect(decisionForScore(40).decision).toBe('NO');
    expect(decisionForScore(54).decision).toBe('NO');
  });

  it('returns STRONG NO for below 40', () => {
    expect(decisionForScore(0).decision).toBe('STRONG NO');
    expect(decisionForScore(39).decision).toBe('STRONG NO');
  });

  it('returns position_size in the result', () => {
    expect(decisionForScore(90).position_size).toBe('FULL SIZE');
    expect(decisionForScore(72).position_size).toBe('STANDARD SIZE');
    expect(decisionForScore(60).position_size).toBe('HALF SIZE');
    expect(decisionForScore(45).position_size).toBe('MINIMAL');
    expect(decisionForScore(10).position_size).toBe('PRESERVE CAPITAL');
  });

  it('boundary: score 85 is STRONG YES, score 84 is YES', () => {
    expect(decisionForScore(85).decision).toBe('STRONG YES');
    expect(decisionForScore(84).decision).toBe('YES');
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
    expect(decisions).toContain('STRONG YES');
    expect(decisions).toContain('YES');
    expect(decisions).toContain('CAUTION');
    expect(decisions).toContain('NO');
    expect(decisions).toContain('STRONG NO');
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
