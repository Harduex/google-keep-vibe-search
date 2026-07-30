# Notes Tab Merge — Design

**Date:** 2026-07-30
**Status:** Approved (design discussion in-session)

## Problem

The Search tab and the All Notes tab are ~70% the same component implemented twice
(`client/src/components/Results.tsx`, 366 LOC, and `client/src/components/AllNotes/index.tsx`,
350 LOC), and the split leaks into the UX:

- Clicking a tag chip in search results teleports to the All Notes tab
  (`handleExploreTag`, `App.tsx`), while the same click in All Notes filters in place.
- Two confusingly similar tag panels: `TagManager` (search-wide tag exclusions,
  delete-tag-everywhere) vs `TagFilter` (include/exclude view filter, rename/merge/export).
- Inconsistent bulk actions: search has bulk Tag but no sort/pinned/archived filters;
  All Notes has the filters but no bulk Tag.
- The duplicated halves have already drifted (e.g. `Results.handleExportTag` re-fetches
  `/api/all-notes` while AllNotes filters its in-memory list).

## Decision

Merge both tabs into a single **Notes** tab backed by one component and one
filter/sort/paging pipeline. Decisions confirmed with the owner:

1. **Unified pipeline** — search results flow through the same tag/pinned/archived
   filters and sort as browsing; searching just narrows the note set.
2. **Relevance sort option** — with an active query the sort dropdown gains
   **Relevance**, which is the default; date sorts remain selectable. Without a query
   the option is absent and default is Last Edited.
3. **One tag panel** — `TagFilter` absorbs `TagManager`'s search-wide exclusion toggle
   and delete-tag-everywhere as per-tag actions; `TagManager` is deleted.
4. **Image search unchanged in placement** — mode toggle + upload render above the
   search bar on the Notes tab, exactly as on the Search tab today; image results
   enter the same pipeline.
5. **Refine kept** — the keyword refinement bar remains, visible only while a query
   is active (it narrows by content keywords; distinct from tag filtering).

## Architecture

### Tabs

`TabId` becomes `'notes' | 'chat' | 'organize'`. `search` and `all-notes` collapse
into `notes` (first position). `handleSearch` and `handleExploreTag` in `App.tsx`
both land on `notes`; `GalleryOverlay`'s `onSwitchTab` and every other `TabId`
reference update accordingly.

### The `Notes` component

New `client/src/components/Notes/` replaces `Results.tsx` and `AllNotes/`. It owns
the single pipeline:

```
source = query active ? search results : all notes
  → tag filter (include/exclude view filter)
  → pinned / archived filters
  → refinement keywords (only when query active)
  → sort (Relevance* | Last Edited | Created)      *only when query active
  → infinite-scroll paging (20 at a time)
```

- **No query** → today's All Notes behavior: full corpus, date sort.
- **Query active** → source switches to ranked search results; Relevance sort
  appears and becomes the selected sort; all filters stay live. "Relevance" order
  is the order the results arrived in.
- **Clearing the query** (✕ affordance in/near the search bar) returns to browse
  mode; the sort falls back to the last chosen date sort (default Last Edited).
- Note cards get the superset of card features in both modes: query-aware
  highlighting, selection, bulk **Tag** and bulk **Export**, show-related,
  show-connections (3D focus), and tag chips that filter **in place** — the
  cross-tab teleport is gone.
- View toggle (list / 3D) preserved. The 3D view always receives the fully
  filtered set, not the paged slice (the existing `filteredNotes`-not-
  `visibleNotes` rule and its explanatory comment carry over).
- Loading skeleton follows the current view mode as `Results` does today.

### Tag panel

`TagFilter` gains two per-tag actions alongside rename/merge/export:

- **Exclude from search** — toggles membership in the search-wide excluded set
  (`/api/tags/excluded`, `useTags.updateExcludedTags`).
- **Delete everywhere** — `useTags.removeTagFromAllNotes` with the existing
  confirmation affordance from `TagManager`.

The view-filter chips (include/exclude for the visible list) and the search-wide
exclusion remain visually and semantically distinct in the panel. The
`TagManager` component is deleted; `TagDialog` (bulk tagging) is kept and now
reachable in both modes.

### State ownership

- `tagFilter` stays lifted in `App` — Organize's Explore still points it at a tag.
- `useSearch` (query, results, refinement) stays in `App`; `Notes` receives it via
  props as `Results` does today.
- Sort, pinned/archived filters, paging count, selection set, view mode, and
  3D focus note stay local to `Notes`.

### Deletions

`client/src/components/Results.tsx`, `client/src/components/AllNotes/`,
`client/src/components/TagManager/` (usages replaced). Roughly 750 LOC replaced by
one ~400 LOC component (split into subcomponents if it grows past that).

## Error handling

- Search errors continue to surface through `useSearch().error` → `ErrorDisplay`.
- All-notes fetch errors render the existing inline error state.
- Bulk tag / excluded-tags updates keep their current try/catch + `console.error`
  boundary behavior.

## Testing

`AllNotes.test.tsx` becomes `Notes.test.tsx`, extended to cover:

- Source switching: no query → all notes; query active → search results.
- Relevance sort: appears only with a query, is the default then, and preserves
  arrival order; date sorts still work on search results.
- Filters (tag/pinned/archived) applying on top of search results.
- Refinement bar visible only with an active query.
- Unified tag panel: exclude-from-search and delete-everywhere actions wired.
- Tag chip click filters in place in both modes.

## Out of scope

- Any backend/API change (none required).
- Moving image search into the search bar (kept as today's mode toggle).
- Organize and Chat tabs beyond the `TabId` rename.
