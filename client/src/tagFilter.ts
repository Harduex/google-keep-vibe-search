import { Note } from '@/types';

/**
 * Which tags the notes list shows and hides.
 *
 * One value rather than two `string[]` states, because the two lists are not independent:
 * a tag held in both would hide exactly the notes its inclusion asked for. Keeping them in
 * one immutable value lets that rule live in one place — the calculations below — instead of
 * being re-derived by every caller that flips a tag.
 */
export interface TagFilterState {
  /** Show only notes carrying at least one of these. Empty means "no restriction". */
  included: string[];
  /** Hide notes carrying any of these. Wins over `included`. */
  excluded: string[];
}

/** How a single tag stands in the filter. */
export type TagFilterMode = 'neutral' | 'included' | 'excluded';

export const EMPTY_TAG_FILTER: TagFilterState = { included: [], excluded: [] };

const without = (tags: string[], tagName: string) => tags.filter((tag) => tag !== tagName);

const toggle = (tags: string[], tagName: string) =>
  tags.includes(tagName) ? without(tags, tagName) : [...tags, tagName];

/** Show only this tag's notes — or stop, if it is already the shown one. */
export function toggleIncluded(state: TagFilterState, tagName: string): TagFilterState {
  return {
    included: toggle(state.included, tagName),
    // Including a tag always clears its exclusion: the two are mutually exclusive, and
    // enforcing that here means no caller can construct the contradiction.
    excluded: without(state.excluded, tagName),
  };
}

/** Hide this tag's notes — or stop hiding them. */
export function toggleExcluded(state: TagFilterState, tagName: string): TagFilterState {
  return {
    included: without(state.included, tagName),
    excluded: toggle(state.excluded, tagName),
  };
}

/**
 * Narrow to exactly one tag, dropping every other inclusion.
 *
 * This is the "explore this tag" gesture, which arrives from outside the notes list (a tag
 * chip in the search results, Explore in the tag manager) and means "show me this", not
 * "add this to what I am already showing".
 */
export function focusTag(state: TagFilterState, tagName: string): TagFilterState {
  return { included: [tagName], excluded: without(state.excluded, tagName) };
}

/** Replace the shown set wholesale, keeping the two sets disjoint. */
export function setIncluded(state: TagFilterState, tagNames: string[]): TagFilterState {
  return {
    included: tagNames,
    excluded: state.excluded.filter((tag) => !tagNames.includes(tag)),
  };
}

/** Replace the hidden set wholesale, keeping the two sets disjoint. */
export function setExcluded(state: TagFilterState, tagNames: string[]): TagFilterState {
  return {
    included: state.included.filter((tag) => !tagNames.includes(tag)),
    excluded: tagNames,
  };
}

/** Back to showing everything. One transition, not one per active tag. */
export function clearTagFilter(): TagFilterState {
  return EMPTY_TAG_FILTER;
}

/** Follow a rename so a filter does not silently stop matching. */
export function renameTagInFilter(
  state: TagFilterState,
  oldName: string,
  newName: string,
): TagFilterState {
  const rename = (tags: string[]) => tags.map((tag) => (tag === oldName ? newName : tag));
  return { included: rename(state.included), excluded: rename(state.excluded) };
}

export function tagFilterMode(state: TagFilterState, tagName: string): TagFilterMode {
  if (state.excluded.includes(tagName)) {
    return 'excluded';
  }
  return state.included.includes(tagName) ? 'included' : 'neutral';
}

export function isFiltering(state: TagFilterState): boolean {
  return state.included.length > 0 || state.excluded.length > 0;
}

/**
 * Human-readable summary of what the filter is doing, for the notes-list count line.
 *
 * A calculation rather than JSX so the pluralisation and the empty cases are testable
 * without rendering a component.
 */
export function describeTagFilter(state: TagFilterState): string {
  const parts = [];
  if (state.included.length > 0) {
    parts.push(`showing ${state.included.length}`);
  }
  if (state.excluded.length > 0) {
    parts.push(`hiding ${state.excluded.length}`);
  }
  if (parts.length === 0) {
    return '';
  }
  const total = state.included.length + state.excluded.length;
  return `${parts.join(', ')} tag${total === 1 ? '' : 's'}`;
}

/**
 * Apply the filter to a note list.
 *
 * Exclusion is evaluated after inclusion, so hiding a tag removes its notes even when
 * another of their tags is included — "hide this" is the stronger statement.
 */
export function applyTagFilter(notes: Note[], state: TagFilterState): Note[] {
  let result = notes;
  if (state.included.length > 0) {
    result = result.filter((note) => note.tags?.some((tag) => state.included.includes(tag)));
  }
  if (state.excluded.length > 0) {
    result = result.filter((note) => !note.tags?.some((tag) => state.excluded.includes(tag)));
  }
  return result;
}
