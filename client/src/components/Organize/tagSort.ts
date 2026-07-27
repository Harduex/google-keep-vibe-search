import { Tag } from '@/types';

/** Sort orders offered for the tag list. */
export type TagSort = 'count-desc' | 'count-asc' | 'name-asc' | 'name-desc';

export const SORT_LABELS: Record<TagSort, string> = {
  'count-desc': 'Most notes',
  'count-asc': 'Fewest notes',
  'name-asc': 'A → Z',
  'name-desc': 'Z → A',
};

/**
 * Order a copy of the tag list.
 *
 * Never sorts in place: `tags` is the cached response object shared by every component
 * that mounts `useTags`, so mutating it would reorder the list under unrelated consumers.
 *
 * Names are compared with `localeCompare`, not `<`. The corpus is multilingual and tag
 * names may be Cyrillic, which a code-point comparison orders after every Latin name
 * rather than alphabetically within its own script; it also sorts every capitalised name
 * ahead of every lowercase one.
 *
 * Ties are broken by the other field so the order is total, and therefore stable across
 * refetches: equal counts fall back to name, equal names to count.
 *
 * Lives in its own module because exporting a non-component from a component file breaks
 * React fast refresh.
 */
export function sortTags(tags: Tag[], sort: TagSort): Tag[] {
  const byName = (a: Tag, b: Tag) => a.name.localeCompare(b.name);
  const sorted = [...tags];
  switch (sort) {
    case 'count-asc':
      return sorted.sort((a, b) => a.count - b.count || byName(a, b));
    case 'name-asc':
      return sorted.sort((a, b) => byName(a, b) || b.count - a.count);
    case 'name-desc':
      return sorted.sort((a, b) => byName(b, a) || b.count - a.count);
    case 'count-desc':
    default:
      return sorted.sort((a, b) => b.count - a.count || byName(a, b));
  }
}
