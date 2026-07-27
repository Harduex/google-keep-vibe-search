import { describe, it, expect } from 'vitest';

import { Tag } from '@/types';

import { sortTags } from '../tagSort';

const tags: Tag[] = [
  { name: 'Travel', count: 12 },
  { name: 'apples', count: 40 },
  { name: 'Работа', count: 12 },
  { name: 'Zebra', count: 3 },
];

const names = (t: Tag[]) => t.map((x) => x.name);

describe('sortTags', () => {
  it('orders by note count, descending', () => {
    expect(names(sortTags(tags, 'count-desc'))).toEqual(['apples', 'Travel', 'Работа', 'Zebra']);
  });

  it('orders by note count, ascending', () => {
    expect(names(sortTags(tags, 'count-asc'))).toEqual(['Zebra', 'Travel', 'Работа', 'apples']);
  });

  it('orders alphabetically, case-insensitively', () => {
    // A code-point comparison would put 'Travel' and 'Zebra' before 'apples' because
    // uppercase letters sort first; localeCompare is what makes this read alphabetically.
    expect(names(sortTags(tags, 'name-asc'))).toEqual(['apples', 'Travel', 'Zebra', 'Работа']);
  });

  it('orders alphabetically in reverse', () => {
    expect(names(sortTags(tags, 'name-desc'))).toEqual(['Работа', 'Zebra', 'Travel', 'apples']);
  });

  it('breaks count ties by name, so the order is total and survives a refetch', () => {
    // Travel and Работа both have 12 notes; without a tiebreak their relative order
    // depends on the incoming array and can flip between refetches.
    const ordered = names(sortTags(tags, 'count-desc'));
    expect(ordered.indexOf('Travel')).toBeLessThan(ordered.indexOf('Работа'));
  });

  it('does not sort the caller-owned array in place', () => {
    // `tags` is the shared cached response; reordering it would reorder the list under
    // every other component that mounts useTags.
    const input: Tag[] = [
      { name: 'b', count: 1 },
      { name: 'a', count: 2 },
    ];
    const before = names(input);
    sortTags(input, 'count-desc');
    expect(names(input)).toEqual(before);
  });
});
