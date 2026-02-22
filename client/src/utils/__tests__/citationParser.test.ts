import { describe, expect, it } from 'vitest';

import type { GroundedContext } from '@/types';

import { buildCitationNumberMap, parseCitations } from '../citationParser';

function makeContext(overrides: Partial<GroundedContext> = {}): GroundedContext {
  return {
    citation_id: 'note1_c0',
    note_id: 'note1',
    note_title: 'Meeting Notes',
    text: 'Budget was approved in Q3.',
    start_char_idx: 0,
    end_char_idx: 25,
    relevance_score: 0.9,
    source_type: 'lancedb',
    heading_trail: [],
    ...overrides,
  };
}

describe('parseCitations', () => {
  it('parses a single citation', () => {
    const ctx = [makeContext()];
    const result = parseCitations('Budget approved [citation:note1_c0] in Q3.', ctx);

    expect(result.citations).toHaveLength(1);
    expect(result.citations[0].citation_id).toBe('note1_c0');
    expect(result.citations[0].note_id).toBe('note1');
    expect(result.segments).toHaveLength(3);
    expect(result.segments[0]).toEqual({ type: 'text', text: 'Budget approved ' });
    expect(result.segments[1]).toEqual({
      type: 'citation',
      text: '[citation:note1_c0]',
      citationId: 'note1_c0',
    });
    expect(result.segments[2]).toEqual({ type: 'text', text: ' in Q3.' });
  });

  it('parses multiple distinct citations', () => {
    const ctx = [
      makeContext({ citation_id: 'a', note_id: 'n1', note_title: 'A' }),
      makeContext({ citation_id: 'b', note_id: 'n2', note_title: 'B' }),
    ];
    const result = parseCitations('Fact [citation:a]. More [citation:b].', ctx);
    expect(result.citations).toHaveLength(2);
  });

  it('deduplicates repeated citations', () => {
    const ctx = [makeContext()];
    const result = parseCitations(
      'First [citation:note1_c0]. Second [citation:note1_c0].',
      ctx,
    );
    expect(result.citations).toHaveLength(1);
    expect(result.segments.filter((s) => s.type === 'citation')).toHaveLength(2);
  });

  it('handles unknown citation IDs gracefully', () => {
    const result = parseCitations('Info [citation:unknown].', []);
    expect(result.citations).toHaveLength(1);
    expect(result.citations[0].note_id).toBe('');
  });

  it('returns plain text when no citations present', () => {
    const result = parseCitations('No citations here.', []);
    expect(result.citations).toHaveLength(0);
    expect(result.segments).toHaveLength(1);
    expect(result.segments[0].type).toBe('text');
  });

  it('strips citations from cleanText', () => {
    const ctx = [makeContext()];
    const result = parseCitations('Budget approved [citation:note1_c0] in Q3.', ctx);
    expect(result.cleanText).toBe('Budget approved in Q3.');
  });

  it('handles citations with surrounding whitespace in ID', () => {
    const ctx = [makeContext()];
    const result = parseCitations('Info [citation: note1_c0 ].', ctx);
    expect(result.citations).toHaveLength(1);
    expect(result.citations[0].citation_id).toBe('note1_c0');
  });

  it('truncates long text_snippet', () => {
    const longText = 'x'.repeat(300);
    const ctx = [makeContext({ text: longText })];
    const result = parseCitations('Info [citation:note1_c0].', ctx);
    expect(result.citations[0].text_snippet.length).toBe(203);
    expect(result.citations[0].text_snippet.endsWith('...')).toBe(true);
  });
});

describe('buildCitationNumberMap', () => {
  it('assigns sequential numbers', () => {
    const citations = [
      { citation_id: 'a', note_id: '', note_title: '', start_char_idx: null, end_char_idx: null, text_snippet: '' },
      { citation_id: 'b', note_id: '', note_title: '', start_char_idx: null, end_char_idx: null, text_snippet: '' },
    ];
    const map = buildCitationNumberMap(citations);
    expect(map.get('a')).toBe(1);
    expect(map.get('b')).toBe(2);
  });

  it('handles duplicates', () => {
    const citations = [
      { citation_id: 'a', note_id: '', note_title: '', start_char_idx: null, end_char_idx: null, text_snippet: '' },
      { citation_id: 'a', note_id: '', note_title: '', start_char_idx: null, end_char_idx: null, text_snippet: '' },
    ];
    const map = buildCitationNumberMap(citations);
    expect(map.size).toBe(1);
    expect(map.get('a')).toBe(1);
  });

  it('returns empty map for empty array', () => {
    const map = buildCitationNumberMap([]);
    expect(map.size).toBe(0);
  });
});
