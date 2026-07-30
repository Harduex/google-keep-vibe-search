import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useSearch } from '@/hooks/useSearch';
import { Note } from '@/types';

const note: Note = {
  id: '1',
  title: 'T',
  content: 'C',
  created: '2025-01-01T00:00:00Z',
  edited: '2025-01-02T00:00:00Z',
  archived: false,
  pinned: false,
  color: 'DEFAULT',
  score: 0.5,
  tags: [],
};

describe('useSearch.clearSearch', () => {
  it('resets results, refinement and hasSearched', () => {
    const { result } = renderHook(() => useSearch());

    // setResults is the fetch-free way to enter the searched state (image search uses it).
    act(() => {
      result.current.setResults([note]);
      result.current.refineResults('kw');
    });
    expect(result.current.hasSearched).toBe(true);

    act(() => {
      result.current.clearSearch();
    });

    expect(result.current.query).toBe('');
    expect(result.current.results).toEqual([]);
    expect(result.current.originalResults).toEqual([]);
    expect(result.current.hasSearched).toBe(false);
    expect(result.current.refinementKeywords).toBe('');
  });
});
