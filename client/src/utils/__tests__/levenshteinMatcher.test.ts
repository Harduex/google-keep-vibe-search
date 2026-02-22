import { describe, expect, it } from 'vitest';

import { findBestMatch, levenshtein } from '../levenshteinMatcher';

describe('levenshtein', () => {
  it('returns 0 for identical strings', () => {
    expect(levenshtein('hello', 'hello')).toBe(0);
  });

  it('returns string length for empty vs non-empty', () => {
    expect(levenshtein('', 'abc')).toBe(3);
    expect(levenshtein('abc', '')).toBe(3);
  });

  it('returns 0 for two empty strings', () => {
    expect(levenshtein('', '')).toBe(0);
  });

  it('counts single substitution', () => {
    expect(levenshtein('abc', 'aXc')).toBe(1);
  });

  it('counts insertion', () => {
    expect(levenshtein('ac', 'abc')).toBe(1);
  });

  it('counts deletion', () => {
    expect(levenshtein('abc', 'ac')).toBe(1);
  });

  it('handles longer strings', () => {
    expect(levenshtein('kitten', 'sitting')).toBe(3);
  });
});

describe('findBestMatch', () => {
  it('returns exact match with distance 0', () => {
    const result = findBestMatch('budget approved', 'The budget approved in Q3.');
    expect(result).not.toBeNull();
    expect(result!.distance).toBe(0);
    expect(result!.start).toBe(4);
    expect(result!.end).toBe(19);
  });

  it('returns null for empty claim', () => {
    expect(findBestMatch('', 'some text')).toBeNull();
  });

  it('returns null for empty source', () => {
    expect(findBestMatch('claim', '')).toBeNull();
  });

  it('finds approximate match within threshold', () => {
    const result = findBestMatch('budgt approved', 'The budget approved in Q3.');
    expect(result).not.toBeNull();
    expect(result!.distance).toBeLessThanOrEqual(0.3);
  });

  it('returns null when no match within threshold', () => {
    const result = findBestMatch('completely different text', 'xyz abc 123');
    expect(result).toBeNull();
  });

  it('is case insensitive', () => {
    const result = findBestMatch('BUDGET APPROVED', 'the budget approved.');
    expect(result).not.toBeNull();
    expect(result!.distance).toBe(0);
  });

  it('handles unicode text', () => {
    const result = findBestMatch('cafe', 'Welcome to the cafe!');
    expect(result).not.toBeNull();
    expect(result!.distance).toBe(0);
  });
});
