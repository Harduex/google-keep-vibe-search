# Tag Exploration — Feature Idea

**Status:** Idea / brainstorm paused (not yet designed or implemented)
**Created:** 2026-07-26
**Seed:** "When I press a tag in the notes list, I would like to explore this tag — how can we achieve good UX for tag exploration?"

## Current state of tags in the app

- **Clicking a tag chip does nothing today.** `NoteCard` (`client/src/components/NoteCard.tsx:153-198`) renders each tag as a `<span className="note-badge badge-tag">`. The badge has no `onClick`; the only handlers are the inline edit (`onRenameTag`) and close (`onRemoveTag`) buttons. A bare click on the label text bubbles up to the card's select/deselect handler (only active in selectable/bulk mode). There is no `onTagClick` / `onFilterByTag` prop on `NoteCard`.
- **Tag data model is flat:** `Tag { name: string; count: number }` (`client/src/types/index.ts:34-41`). No color, hierarchy, or co-occurrence metadata. (`tagColors.ts` only colors tags in the 3D embeddings view, not the notes list.)
- **Existing "filter by tag" is a separate checkbox panel**, only in the **All Notes** tab: `TagFilter` (`client/src/components/TagFilter/index.tsx`) drives `selectedTags` state (`AllNotes/index.tsx:27`), client-side OR-filtering over `/api/all-notes` (`AllNotes/index.tsx:36-37`).
- **Search/Results tab has no inclusive tag filter** — only tag *exclusion* via `TagManager`.
- **Backend gaps relevant to exploration:**
  - No "notes for a given tag" endpoint — the client always pulls `/api/all-notes` and filters in JS.
  - No tag co-occurrence / "related tags" endpoint.
  - The inclusive OR-tag filter primitive *does* exist server-side (`SearchService.in_scope`, used by the chat agent's `filter_by_tag` tool) but is not wired to any HTTP endpoint.
- **Unusual leverage already in the repo:** an embeddings + HDBSCAN clustering + c-TF-IDF categorization pipeline (`app/services/tagging/`, `categorization_service.py`) and a 3D embeddings visualization. A tag could open an explorable map rather than just a flat list.

## The central question (resolve before designing)

**What does "explore this tag" mean to the user?** This fork determines everything downstream:

- **A) Simple filter** — click tag → list narrows to that tag's notes (parity with most note apps). Low effort, reuses existing `selectedTags` pattern.
- **B) Relatedness / neighborhood** — clicking surfaces co-occurring tags, sub-topics, and related-but-different tags. Needs a new co-occurrence endpoint; builds on clustering.
- **C) Explorable map** — tag opens a small spatial/cluster view of its notes (reuse the embeddings viz). Highest effort, most novel.

Other open sub-questions to settle once the above is picked:
- Should the click be a toggle (filter on/off) or a navigation (open a dedicated tag view)?
- Multi-select (AND/OR) vs single-tag focus?
- Should the same affordance work in the Search/Results tab, which currently has no inclusive filter?
- Server-side "notes by tag" endpoint vs continued client-side filtering over `/api/all-notes`.

## How to resume

1. Decide the answer to the central question above (A / B / C, or a blend).
2. Resume the `superpowers:brainstorming` flow from the clarifying-questions step — the project context is already gathered (see "Current state" above).
3. Continue through propose-approaches → design → spec → `writing-plans`.
