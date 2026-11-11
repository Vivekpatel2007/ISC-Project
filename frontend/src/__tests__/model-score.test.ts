import { describe, expect, it } from 'vitest';
import { formatModelScore } from '@/lib/utils';

describe('Model score display', () => {
  it.each([1, .999999, .99999999])('does not display a rounded or saturated score as absolute certainty (%s)', (value) => {
    expect(formatModelScore(value)).toBe('>99.99%');
  });
  it.each([0, .00000001])('labels scores near zero without claiming absolute zero (%s)', (value) => {
    expect(formatModelScore(value)).toBe('<0.01%');
  });
  it('preserves ordinary percentage scores', () => {
    expect(formatModelScore(.954)).toBe('95.40%');
    expect(formatModelScore(.5)).toBe('50.00%');
  });
  it.each([NaN, Infinity, -1, 1.01])('does not invent a score for invalid input (%s)', (value) => {
    expect(formatModelScore(value)).toBe('Unavailable');
  });
});
