import { describe, expect, it } from 'vitest';

import {
  EMPTY_TAG_FILTER,
  TagFilterState,
  applyTagFilter,
  clearTagFilter,
  describeTagFilter,
  focusTag,
  isFiltering,
  renameTagInFilter,
  setExcluded,
  setIncluded,
  tagFilterMode,
  toggleExcluded,
  toggleIncluded,
} from '@/tagFilter';
import { Note } from '@/types';

const note = (id: string, tags: string[]): Note => ({
  id,
  title: id,
  content: '',
  created: '2025-01-01T00:00:00Z',
  edited: '2025-01-01T00:00:00Z',
  archived: false,
  pinned: false,
  color: 'DEFAULT',
  score: 0,
  tags,
});

describe('tag filter state', () => {
  it('keeps the two sets disjoint however a tag is flipped', () => {
    const included = toggleIncluded(EMPTY_TAG_FILTER, 'Work');
    expect(included).toEqual({ included: ['Work'], excluded: [] });

    // Excluding a shown tag moves it across rather than holding both.
    const excluded = toggleExcluded(included, 'Work');
    expect(excluded).toEqual({ included: [], excluded: ['Work'] });

    // And back again.
    expect(toggleIncluded(excluded, 'Work')).toEqual({ included: ['Work'], excluded: [] });
  });

  it('toggles a tag back off rather than accumulating duplicates', () => {
    const once = toggleIncluded(EMPTY_TAG_FILTER, 'Work');
    expect(toggleIncluded(once, 'Work').included).toEqual([]);

    const twice = toggleIncluded(once, 'Ideas');
    expect(twice.included).toEqual(['Work', 'Ideas']);
  });

  it('never mutates the state it is given', () => {
    const state: TagFilterState = { included: ['Work'], excluded: ['Spam'] };
    const frozen = { included: [...state.included], excluded: [...state.excluded] };

    toggleIncluded(state, 'Ideas');
    toggleExcluded(state, 'Work');
    focusTag(state, 'Ideas');
    setIncluded(state, ['Other']);
    renameTagInFilter(state, 'Work', 'Job');

    expect(state).toEqual(frozen);
  });

  it('focusTag narrows to one tag instead of widening the selection', () => {
    const state: TagFilterState = { included: ['Work', 'Ideas'], excluded: ['Travel'] };
    expect(focusTag(state, 'Travel')).toEqual({ included: ['Travel'], excluded: [] });
  });

  it('setIncluded and setExcluded drop conflicts from the other set', () => {
    const state: TagFilterState = { included: ['Work'], excluded: ['Spam'] };
    expect(setIncluded(state, ['Spam'])).toEqual({ included: ['Spam'], excluded: [] });
    expect(setExcluded(state, ['Work'])).toEqual({ included: [], excluded: ['Work'] });
  });

  it('clears both sets at once', () => {
    expect(clearTagFilter()).toEqual(EMPTY_TAG_FILTER);
  });

  it('follows a rename in both sets', () => {
    const state: TagFilterState = { included: ['Work'], excluded: ['Spam'] };
    expect(renameTagInFilter(state, 'Work', 'Job').included).toEqual(['Job']);
    expect(renameTagInFilter(state, 'Spam', 'Junk').excluded).toEqual(['Junk']);
  });

  it('reports each tag mode, with exclusion taking precedence', () => {
    const state: TagFilterState = { included: ['Work'], excluded: ['Spam'] };
    expect(tagFilterMode(state, 'Work')).toBe('included');
    expect(tagFilterMode(state, 'Spam')).toBe('excluded');
    expect(tagFilterMode(state, 'Other')).toBe('neutral');
    expect(isFiltering(state)).toBe(true);
    expect(isFiltering(EMPTY_TAG_FILTER)).toBe(false);
  });
});

describe('describeTagFilter', () => {
  it('summarises each combination, pluralising on the total', () => {
    expect(describeTagFilter(EMPTY_TAG_FILTER)).toBe('');
    expect(describeTagFilter({ included: ['a'], excluded: [] })).toBe('showing 1 tag');
    expect(describeTagFilter({ included: [], excluded: ['a'] })).toBe('hiding 1 tag');
    expect(describeTagFilter({ included: ['a'], excluded: ['b'] })).toBe(
      'showing 1, hiding 1 tags',
    );
    expect(describeTagFilter({ included: ['a', 'b'], excluded: [] })).toBe('showing 2 tags');
  });
});

describe('applyTagFilter', () => {
  const notes = [note('a', ['Work']), note('b', ['Ideas']), note('c', ['Work', 'Spam'])];

  it('passes everything through when nothing is filtered', () => {
    expect(applyTagFilter(notes, EMPTY_TAG_FILTER)).toEqual(notes);
  });

  it('keeps notes carrying any included tag', () => {
    const kept = applyTagFilter(notes, { included: ['Work'], excluded: [] });
    expect(kept.map((n) => n.id)).toEqual(['a', 'c']);
  });

  it('lets an exclusion beat an inclusion on the same note', () => {
    // Note c is both Work (shown) and Spam (hidden) — hiding is the stronger statement.
    const kept = applyTagFilter(notes, { included: ['Work'], excluded: ['Spam'] });
    expect(kept.map((n) => n.id)).toEqual(['a']);
  });

  it('handles notes with no tags at all', () => {
    const untagged = [note('d', [])];
    expect(applyTagFilter(untagged, { included: ['Work'], excluded: [] })).toEqual([]);
    expect(applyTagFilter(untagged, { included: [], excluded: ['Work'] })).toEqual(untagged);
  });
});
