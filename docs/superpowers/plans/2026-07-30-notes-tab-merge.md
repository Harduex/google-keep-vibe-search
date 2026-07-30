# Notes Tab Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the Search and All Notes tabs into a single Notes tab backed by one component and one filter/sort/paging pipeline.

**Architecture:** A new `client/src/components/Notes/` component replaces `Results.tsx` and `AllNotes/`. Its source set is search results when a query is active, otherwise all notes; both flow through the same tag/pinned/archived filters, sort (with a Relevance option that exists only during search), and infinite-scroll paging. `TagFilter` absorbs `TagManager`'s search-wide-exclusion and delete-everywhere actions; `TagManager` is deleted. Spec: `docs/superpowers/specs/2026-07-30-notes-tab-merge-design.md`.

**Tech Stack:** React 19 + TypeScript, Vite 6, Vitest + Testing Library (frontend only; zero backend changes).

## Global Constraints

- Never read real note contents; test fixtures use synthetic notes only (see AGENTS.md privacy boundary).
- Frontend checks run from `client/`: `npx vitest run` (tests), `npx tsc --noEmit` (types), `npm run lint` (lint).
- Commits: conventional-commit style, **no** Co-Authored-By trailer, never push.
- Pre-commit hooks run prettier; if prettier fights a construct (`??` in ternary, nested ternaries), rewrite the code instead of fighting the formatter.
- Follow existing patterns: `memo`-wrapped components, `useCallback` handlers, `createXHandler` factories for per-item handlers, CSS files co-located per component.

---

### Task 1: `clearSearch` in `useSearch`

Returning from search mode to browse mode needs one call that resets query, results, refinement, and `hasSearched`. Nothing provides that today.

**Files:**

- Modify: `client/src/hooks/useSearch.ts`
- Test: `client/src/hooks/__tests__/useSearch.clearSearch.test.ts` (create)

**Interfaces:**

- Produces: `useSearch()` return gains `clearSearch: () => void`. After calling it: `query === ''`, `results === []`, `originalResults === []`, `hasSearched === false`, `refinementKeywords === ''`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/hooks/__tests__/useSearch.clearSearch.test.ts
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useSearch } from "@/hooks/useSearch";
import { Note } from "@/types";

const note: Note = {
  id: "1",
  title: "T",
  content: "C",
  created: "2025-01-01T00:00:00Z",
  edited: "2025-01-02T00:00:00Z",
  archived: false,
  pinned: false,
  color: "DEFAULT",
  score: 0.5,
  tags: [],
};

describe("useSearch.clearSearch", () => {
  it("resets results, refinement and hasSearched", () => {
    const { result } = renderHook(() => useSearch());

    // setResults is the fetch-free way to enter the searched state (image search uses it).
    act(() => {
      result.current.setResults([note]);
      result.current.refineResults("kw");
    });
    expect(result.current.hasSearched).toBe(true);

    act(() => {
      result.current.clearSearch();
    });

    expect(result.current.query).toBe("");
    expect(result.current.results).toEqual([]);
    expect(result.current.originalResults).toEqual([]);
    expect(result.current.hasSearched).toBe(false);
    expect(result.current.refinementKeywords).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/hooks/__tests__/useSearch.clearSearch.test.ts`
Expected: FAIL — `result.current.clearSearch is not a function`

- [ ] **Step 3: Implement `clearSearch`**

In `client/src/hooks/useSearch.ts`, add to the `UseSearchResult` interface (after `setLoading`):

```ts
  clearSearch: () => void; // Back to browse mode: no query, no results, no refinement
```

Add the callback in the hook body (after `setLoading`):

```ts
// Leave search mode entirely — the Notes tab falls back to browsing all notes.
const clearSearch = useCallback(() => {
  setQuery("");
  setOriginalResults([]);
  setRefinementKeywords("");
  setHasSearched(false);
  clearError();
}, [clearError]);
```

Add `clearSearch,` to the returned object.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/hooks/__tests__/useSearch.clearSearch.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useSearch.ts client/src/hooks/__tests__/useSearch.clearSearch.test.ts
git commit -m "feat(search): add clearSearch to useSearch for returning to browse mode"
```

---

### Task 2: Clear (✕) button in `SearchBar`

**Files:**

- Modify: `client/src/components/SearchBar.tsx`
- Test: `client/src/components/__tests__/SearchBar.test.tsx` (create)

**Interfaces:**

- Consumes: nothing new.
- Produces: `SearchBarProps` gains optional `onClear?: () => void`. A button labelled `Clear search` renders only while the input is non-empty; clicking it empties the input and calls `onClear`.

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/components/__tests__/SearchBar.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SearchBar } from "@/components/SearchBar";

describe("SearchBar clear button", () => {
  it("is absent when the input is empty", () => {
    render(<SearchBar onSearch={vi.fn()} onClear={vi.fn()} />);
    expect(
      screen.queryByRole("button", { name: "Clear search" }),
    ).not.toBeInTheDocument();
  });

  it("clears the input and notifies the owner", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(
      <SearchBar
        onSearch={vi.fn()}
        onClear={onClear}
        currentQuery="groceries"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Clear search" }));

    expect(onClear).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText(/Search your notes/)).toHaveValue("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/components/__tests__/SearchBar.test.tsx`
Expected: FAIL — clear button not found / `onClear` prop unknown

- [ ] **Step 3: Implement the button**

Replace `client/src/components/SearchBar.tsx` content with:

```tsx
import { FormEvent, useState, memo, useCallback, useEffect } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  /** Leave search mode: the owner drops the query and its results. */
  onClear?: () => void;
  currentQuery?: string;
}

export const SearchBar = memo(
  ({ onSearch, onClear, currentQuery = "" }: SearchBarProps) => {
    const [inputValue, setInputValue] = useState(currentQuery);

    useEffect(() => {
      setInputValue(currentQuery);
    }, [currentQuery]);

    const handleSubmit = useCallback(
      (e: FormEvent) => {
        e.preventDefault();
        onSearch(inputValue);
      },
      [inputValue, onSearch],
    );

    const handleInputChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        setInputValue(e.target.value);
      },
      [],
    );

    const handleClear = useCallback(() => {
      setInputValue("");
      onClear?.();
    }, [onClear]);

    return (
      <div className="search-container">
        <form
          onSubmit={handleSubmit}
          style={{ display: "flex", width: "100%" }}
        >
          <input
            type="text"
            id="search-input"
            placeholder="Search your notes by keywords or vibes..."
            value={inputValue}
            onChange={handleInputChange}
            autoFocus
          />
          {inputValue !== "" && (
            <button
              type="button"
              className="search-clear-button"
              onClick={handleClear}
              title="Clear search"
              aria-label="Clear search"
            >
              <span className="material-icons">close</span>
            </button>
          )}
          <button id="search-button" type="submit">
            Search
          </button>
        </form>
      </div>
    );
  },
);
```

Add to `client/src/App.css` (next to the existing `.search-container` rules — find them with `grep -n "search-container" client/src/App.css`):

```css
.search-clear-button {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary, #666);
  display: flex;
  align-items: center;
  padding: 0 8px;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/components/__tests__/SearchBar.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/components/SearchBar.tsx client/src/components/__tests__/SearchBar.test.tsx client/src/App.css
git commit -m "feat(search): add a clear button to the search bar"
```

---

### Task 3: `TagFilter` absorbs `TagManager`'s actions

`TagManager` has exactly two behaviors `TagFilter` lacks: toggling a tag's membership in the **search-wide** excluded set (`/api/tags/excluded`) and deleting a tag from all notes. Add both as per-tag row actions. `TagManager` itself is deleted in Task 5.

**Files:**

- Modify: `client/src/components/TagFilter/index.tsx`
- Modify: `client/src/components/TagFilter/styles.css`
- Test: `client/src/components/__tests__/TagFilter.actions.test.tsx` (create)

**Interfaces:**

- Consumes: `useTags().excludedTags: string[]`, `useTags().updateExcludedTags(tags: string[])`, `useTags().removeTagFromAllNotes(tagName: string)` (existing, called by the owner — Task 4 wires them).
- Produces: `TagFilterProps` gains:

  - `searchExcludedTags?: string[]` — tags currently excluded from search (server-side set).
  - `onToggleSearchExcluded?: (tagName: string) => void` — flip one tag's search-wide exclusion.
  - `onDeleteTagEverywhere?: (tagName: string) => void` — remove the tag from every note (the component asks `window.confirm` first; the handler is called only on confirm).

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/components/__tests__/TagFilter.actions.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TagFilter } from "@/components/TagFilter";
import { EMPTY_TAG_FILTER } from "@/tagFilter";
import { Tag } from "@/types";

const tags: Tag[] = [
  { name: "Work", count: 3 },
  { name: "Ideas", count: 2 },
];

const baseProps = {
  tags,
  filter: EMPTY_TAG_FILTER,
  onUpdateSelectedTags: vi.fn(),
  onToggleExcluded: vi.fn(),
  onClearFilter: vi.fn(),
};

describe("TagFilter search-wide actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("toggles a tag in and out of the search-wide excluded set", async () => {
    const user = userEvent.setup();
    const onToggleSearchExcluded = vi.fn();
    render(
      <TagFilter
        {...baseProps}
        searchExcludedTags={["Ideas"]}
        onToggleSearchExcluded={onToggleSearchExcluded}
      />,
    );

    await user.click(screen.getByText("Filter by Tags"));

    // An already-excluded tag reads as such and offers re-inclusion.
    const ideasButton = screen.getByRole("button", {
      name: 'Include "Ideas" in search results again',
    });
    expect(ideasButton).toHaveAttribute("aria-pressed", "true");

    await user.click(
      screen.getByRole("button", {
        name: 'Exclude "Work" from search results',
      }),
    );
    expect(onToggleSearchExcluded).toHaveBeenCalledWith("Work");
  });

  it("confirms before deleting a tag everywhere", async () => {
    const user = userEvent.setup();
    const onDeleteTagEverywhere = vi.fn();
    render(
      <TagFilter
        {...baseProps}
        onDeleteTagEverywhere={onDeleteTagEverywhere}
      />,
    );

    await user.click(screen.getByText("Filter by Tags"));
    await user.click(
      screen.getByRole("button", { name: 'Delete tag "Work" from all notes' }),
    );

    expect(window.confirm).toHaveBeenCalledWith(
      'Are you sure you want to remove the tag "Work" from all notes?',
    );
    expect(onDeleteTagEverywhere).toHaveBeenCalledWith("Work");
  });

  it("does not delete when the confirm is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    const onDeleteTagEverywhere = vi.fn();
    render(
      <TagFilter
        {...baseProps}
        onDeleteTagEverywhere={onDeleteTagEverywhere}
      />,
    );

    await user.click(screen.getByText("Filter by Tags"));
    await user.click(
      screen.getByRole("button", { name: 'Delete tag "Work" from all notes' }),
    );

    expect(onDeleteTagEverywhere).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/components/__tests__/TagFilter.actions.test.tsx`
Expected: FAIL — buttons not found

- [ ] **Step 3: Implement the new props and row actions**

In `client/src/components/TagFilter/index.tsx`:

1. Extend the props interface (after `onExportTag`):

```ts
  /** Tags excluded search-wide (the /api/tags/excluded set — not the view filter). */
  searchExcludedTags?: string[];
  /** Flip one tag's search-wide exclusion. */
  onToggleSearchExcluded?: (tagName: string) => void;
  /** Remove the tag from every note carrying it. Confirmation happens here. */
  onDeleteTagEverywhere?: (tagName: string) => void;
```

2. Destructure `searchExcludedTags = [], onToggleSearchExcluded, onDeleteTagEverywhere` in the component signature.

3. Add handler factories next to `createExportTagHandler`:

```ts
const createSearchExcludeHandler = useCallback(
  (tagName: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleSearchExcluded?.(tagName);
  },
  [onToggleSearchExcluded],
);

const createDeleteEverywhereHandler = useCallback(
  (tagName: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    if (
      window.confirm(
        `Are you sure you want to remove the tag "${tagName}" from all notes?`,
      )
    ) {
      onDeleteTagEverywhere?.(tagName);
    }
  },
  [onDeleteTagEverywhere],
);
```

4. In the tag-row JSX, inside `<div className="tag-row-actions">`, insert **between** the export button and the show/hide segmented control:

```tsx
{
  onToggleSearchExcluded && (
    <button
      className={`search-exclude-button${
        searchExcludedTags.includes(tag.name) ? " active" : ""
      }`}
      onClick={createSearchExcludeHandler(tag.name)}
      aria-pressed={searchExcludedTags.includes(tag.name)}
      title={
        searchExcludedTags.includes(tag.name)
          ? `Include "${tag.name}" in search results again`
          : `Exclude "${tag.name}" from search results`
      }
      aria-label={
        searchExcludedTags.includes(tag.name)
          ? `Include "${tag.name}" in search results again`
          : `Exclude "${tag.name}" from search results`
      }
    >
      <span className="material-icons">search_off</span>
    </button>
  );
}
{
  onDeleteTagEverywhere && (
    <button
      className="delete-tag-button"
      onClick={createDeleteEverywhereHandler(tag.name)}
      title={`Delete tag "${tag.name}" from all notes`}
      aria-label={`Delete tag "${tag.name}" from all notes`}
    >
      <span className="material-icons">delete_forever</span>
    </button>
  );
}
```

5. Extend the help footer text (the `tag-filter-help` block) — replace its `<span>` text with:

```
Select tags to show only notes with those tags; when nothing is selected, all notes are
displayed. The block icon hides a tag's notes instead, and wins over a selection. The
search-off icon excludes a tag from search results entirely; the trash icon deletes the
tag from every note. Select multiple tags to merge them into one of the selected tags.
```

6. In `client/src/components/TagFilter/styles.css`, add alongside the existing `.export-tag-button` rules (copy its base styling — find it with `grep -n "export-tag-button" client/src/components/TagFilter/styles.css`):

```css
.search-exclude-button,
.delete-tag-button {
  /* mirror .export-tag-button's declarations here */
}

.search-exclude-button.active {
  color: var(--accent-color, #fbbc04);
}

.delete-tag-button:hover {
  color: #d93025;
}
```

- [ ] **Step 4: Run new and existing tests**

Run: `cd client && npx vitest run src/components/__tests__/TagFilter.actions.test.tsx src/components/__tests__/AllNotes.test.tsx`
Expected: PASS (AllNotes passes untouched — the new props are optional)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/TagFilter/ client/src/components/__tests__/TagFilter.actions.test.tsx
git commit -m "feat(tags): add search-wide exclusion and delete-everywhere actions to TagFilter"
```

---

### Task 4: The `Notes` component (unified pipeline)

The heart of the merge. One component, one pipeline; browse mode when no search is active, search mode when one is.

**Files:**

- Create: `client/src/components/Notes/index.tsx`
- Create: `client/src/components/Notes/styles.css` (copy of `client/src/components/AllNotes/styles.css` — class names are kept)
- Test: `client/src/components/__tests__/Notes.test.tsx` (create; ports the four `AllNotes.test.tsx` cases and adds search-mode cases. `AllNotes.test.tsx` is deleted in Task 5.)

**Interfaces:**

- Consumes: `useAllNotes()`, `useTags(onNotesChanged)`, `TagFilter` incl. Task 3 props, `TagDialog`, `RefinementSearchBar`, `NoteCard`, `NoteSkeleton`, `ViewToggle`, `Visualization`, `ScrollToTop`, `applyTagFilter`/`toggleIncluded`/`toggleExcluded`/`setIncluded`/`clearTagFilter`/`renameTagInFilter`/`isFiltering`/`describeTagFilter` from `@/tagFilter`, `exportNotes`/`todayDateStr` from `@/exportUtils`, `VIEW_MODES` from `@/const`.
- Produces:

```ts
export type NotesSortBy = "relevance" | "edited" | "created";

interface NotesProps {
  // Search state (owned by App via useSearch)
  query: string;
  results: Note[];
  originalResults: Note[];
  refinementKeywords: string;
  isSearchLoading: boolean;
  hasSearched: boolean;
  isRefined: boolean;
  onRefine: (keywords: string) => void;
  onResetRefinement: () => void;
  onClearSearch: () => void;
  /** Re-run the active search after a mutation (App re-POSTs the query). */
  onResultsUpdate: () => void;
  // Shared
  onShowRelated: (content: string) => void;
  tagFilter: TagFilterState;
  onTagFilterChange: Dispatch<SetStateAction<TagFilterState>>;
}

export const Notes: React.MemoExoticComponent<
  (props: NotesProps) => JSX.Element
>;
```

- [ ] **Step 1: Write the failing tests**

```tsx
// client/src/components/__tests__/Notes.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Notes } from "@/components/Notes";
import { useAllNotes } from "@/hooks/useAllNotes";
import { useTags } from "@/hooks/useTags";
import { EMPTY_TAG_FILTER } from "@/tagFilter";
import { Note, Tag } from "@/types";

vi.mock("@/hooks/useAllNotes");
vi.mock("@/hooks/useTags");

vi.mock("@/components/NoteCard", () => ({
  NoteCard: ({ note }: { note: Note }) => (
    <div data-testid="note-card">{note.title}</div>
  ),
}));

vi.mock("@/components/NoteSkeleton", () => ({
  NoteSkeleton: () => <div data-testid="note-skeleton" />,
}));

vi.mock("@/components/ScrollToTop", () => ({
  ScrollToTop: () => null,
}));

vi.mock("@/components/ViewToggle", () => ({
  ViewToggle: () => <div data-testid="view-toggle" />,
}));

vi.mock("@/components/Visualization", () => ({
  Visualization: () => <div data-testid="visualization" />,
}));

vi.mock("@/components/RefinementSearchBar", () => ({
  RefinementSearchBar: () => <div data-testid="refinement-bar" />,
}));

const mockUseAllNotes = vi.mocked(useAllNotes);
const mockUseTags = vi.mocked(useTags);

const tags: Tag[] = [
  { name: "Work", count: 3 },
  { name: "Ideas", count: 2 },
  { name: "Travel", count: 1 },
];

const makeNote = (overrides: Partial<Note>): Note => ({
  id: "x",
  title: "Untitled",
  content: "",
  created: "2025-01-01T00:00:00Z",
  edited: "2025-01-02T00:00:00Z",
  archived: false,
  pinned: false,
  color: "DEFAULT",
  score: 0,
  tags: [],
  ...overrides,
});

const allNotes: Note[] = [
  makeNote({
    id: "1",
    title: "First",
    tags: ["Work"],
    edited: "2025-01-02T00:00:00Z",
  }),
  makeNote({
    id: "2",
    title: "Second",
    tags: ["Ideas"],
    edited: "2025-01-04T00:00:00Z",
  }),
  makeNote({
    id: "3",
    title: "Third",
    tags: ["Travel"],
    edited: "2025-01-06T00:00:00Z",
  }),
];

// Relevance order deliberately disagrees with date order: '1' (older) ranks first.
const searchResults: Note[] = [
  makeNote({
    id: "1",
    title: "First",
    tags: ["Work"],
    score: 0.9,
    edited: "2025-01-02T00:00:00Z",
  }),
  makeNote({
    id: "3",
    title: "Third",
    tags: ["Travel"],
    score: 0.4,
    edited: "2025-01-06T00:00:00Z",
  }),
];

interface HarnessProps {
  hasSearched?: boolean;
  results?: Note[];
  query?: string;
  onClearSearch?: () => void;
}

/** The tag filter and search state are owned by App, so tests need a stateful owner. */
const StatefulNotes = ({
  hasSearched = false,
  results = [],
  query = "",
  onClearSearch = vi.fn(),
}: HarnessProps) => {
  const [tagFilter, setTagFilter] = useState(EMPTY_TAG_FILTER);
  return (
    <Notes
      query={query}
      results={results}
      originalResults={results}
      refinementKeywords=""
      isSearchLoading={false}
      hasSearched={hasSearched}
      isRefined={false}
      onRefine={vi.fn()}
      onResetRefinement={vi.fn()}
      onClearSearch={onClearSearch}
      onResultsUpdate={vi.fn()}
      onShowRelated={vi.fn()}
      tagFilter={tagFilter}
      onTagFilterChange={setTagFilter}
    />
  );
};

const showOnly = (tagName: string) =>
  screen.getByRole("button", { name: `Show only notes tagged "${tagName}"` });
const hide = (tagName: string) =>
  screen.getByRole("button", { name: `Hide notes tagged "${tagName}"` });

describe("Notes", () => {
  const renameTag = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAllNotes.mockReturnValue({
      notes: allNotes,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseTags.mockReturnValue({
      tags,
      excludedTags: [],
      isLoading: false,
      error: null,
      tagNotes: vi.fn(),
      updateExcludedTags: vi.fn(),
      removeTagFromNote: vi.fn(),
      removeTagFromAllNotes: vi.fn(),
      removeAllTags: vi.fn(),
      renameTag,
      refetchTags: vi.fn(),
      refetchExcludedTags: vi.fn(),
      coverage: null,
      isCoverageLoading: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  describe("browse mode (no active search)", () => {
    it("shows the full corpus sorted by last edited, without a Relevance option", () => {
      render(<StatefulNotes />);

      const cards = screen.getAllByTestId("note-card");
      expect(cards.map((c) => c.textContent)).toEqual([
        "Third",
        "Second",
        "First",
      ]);
      expect(
        screen.queryByRole("option", { name: "Sort by Relevance" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Clear search" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Refine/ }),
      ).not.toBeInTheDocument();
    });
  });

  describe("search mode", () => {
    it("shows results in relevance order by default, with a Relevance sort option", () => {
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      const cards = screen.getAllByTestId("note-card");
      expect(cards.map((c) => c.textContent)).toEqual(["First", "Third"]);

      const sortSelect = screen.getByRole("combobox");
      expect(sortSelect).toHaveValue("relevance");
      expect(
        screen.getByRole("option", { name: "Sort by Relevance" }),
      ).toBeInTheDocument();
    });

    it("can re-sort search results by date", async () => {
      const user = userEvent.setup();
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      await user.selectOptions(screen.getByRole("combobox"), "edited");

      const cards = screen.getAllByTestId("note-card");
      expect(cards.map((c) => c.textContent)).toEqual(["Third", "First"]);
    });

    it("applies the tag view filter on top of search results", async () => {
      const user = userEvent.setup();
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      await user.click(screen.getByText("Filter by Tags"));
      await user.click(showOnly("Work"));

      const cards = screen.getAllByTestId("note-card");
      expect(cards.map((c) => c.textContent)).toEqual(["First"]);
    });

    it("offers Refine and Clear search only while searching", () => {
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      expect(
        screen.getByRole("button", { name: /Refine/ }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Clear search" }),
      ).toBeInTheDocument();
    });

    it("clearing the search hands control back to the owner", async () => {
      const user = userEvent.setup();
      const onClearSearch = vi.fn();
      render(
        <StatefulNotes
          hasSearched
          results={searchResults}
          query="q"
          onClearSearch={onClearSearch}
        />,
      );

      await user.click(screen.getByRole("button", { name: "Clear search" }));
      expect(onClearSearch).toHaveBeenCalledTimes(1);
    });

    it("shows the search empty state when results are empty", () => {
      render(<StatefulNotes hasSearched results={[]} query="q" />);
      expect(screen.getByText("No matching notes found.")).toBeInTheDocument();
    });
  });

  // Ported from AllNotes.test.tsx — the merge must not regress tag-filter behavior.
  describe("tag merge from filter", () => {
    it("shows merge only after selecting more than one tag", async () => {
      const user = userEvent.setup();
      render(<StatefulNotes />);

      await user.click(screen.getByText("Filter by Tags"));
      expect(
        screen.queryByRole("button", { name: "Merge Selected" }),
      ).not.toBeInTheDocument();

      await user.click(showOnly("Work"));
      expect(
        screen.queryByRole("button", { name: "Merge Selected" }),
      ).not.toBeInTheDocument();

      await user.click(showOnly("Ideas"));
      expect(
        screen.getByRole("button", { name: "Merge Selected" }),
      ).toBeInTheDocument();
    });

    it("merges selected tags into the chosen selected target", async () => {
      const user = userEvent.setup();
      render(<StatefulNotes />);

      await user.click(screen.getByText("Filter by Tags"));
      await user.click(showOnly("Work"));
      await user.click(showOnly("Ideas"));
      await user.click(screen.getByRole("button", { name: "Merge Selected" }));

      expect(screen.getByText("Keep this tag:")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Work" }));

      await waitFor(() => {
        expect(renameTag).toHaveBeenCalledWith("Ideas", "Work");
      });
      expect(renameTag).toHaveBeenCalledTimes(1);
    });

    it("excluding a tag hides its notes and clears any selection of it", async () => {
      const user = userEvent.setup();
      render(<StatefulNotes />);

      await user.click(screen.getByText("Filter by Tags"));
      await user.click(showOnly("Work"));
      await user.click(hide("Work"));

      expect(showOnly("Work")).toHaveAttribute("aria-pressed", "false");
      expect(
        screen.getByRole("button", { name: 'Stop hiding "Work"' }),
      ).toBeInTheDocument();
      expect(screen.getAllByTestId("note-card")).toHaveLength(2);
    });

    it("makes the filter panel sticky only while a filter is applied", async () => {
      const user = userEvent.setup();
      const { container } = render(<StatefulNotes />);

      expect(container.querySelector(".tag-filter")).not.toHaveClass("sticky");

      await user.click(screen.getByText("Filter by Tags"));
      await user.click(showOnly("Work"));
      expect(container.querySelector(".tag-filter")).toHaveClass("sticky");

      await user.click(showOnly("Work"));
      expect(container.querySelector(".tag-filter")).not.toHaveClass("sticky");
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/components/__tests__/Notes.test.tsx`
Expected: FAIL — module `@/components/Notes` not found

- [ ] **Step 3: Create the styles**

```bash
mkdir -p client/src/components/Notes
cp client/src/components/AllNotes/styles.css client/src/components/Notes/styles.css
```

Then append to `client/src/components/Notes/styles.css` (search-mode additions; `refined-filter-info` already exists in `App.css` — check with `grep -rn "refined-filter-info\|clear-search-button" client/src` and only add what's missing):

```css
.clear-search-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 12px;
  background: none;
  border: 1px solid var(--border-color, #dadce0);
  border-radius: 16px;
  padding: 2px 10px;
  cursor: pointer;
  color: inherit;
  font-size: 0.85em;
}
```

- [ ] **Step 4: Write the component**

```tsx
// client/src/components/Notes/index.tsx
import {
  Dispatch,
  SetStateAction,
  memo,
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
} from "react";

import { NoteCard } from "@/components/NoteCard";
import { NoteSkeleton } from "@/components/NoteSkeleton";
import { RefinementSearchBar } from "@/components/RefinementSearchBar";
import { ScrollToTop } from "@/components/ScrollToTop";
import { TagDialog } from "@/components/TagDialog";
import { TagFilter } from "@/components/TagFilter";
import { ViewToggle } from "@/components/ViewToggle";
import { Visualization } from "@/components/Visualization";
import { VIEW_MODES } from "@/const";
import { exportNotes, todayDateStr } from "@/exportUtils";
import { useAllNotes } from "@/hooks/useAllNotes";
import { useTags } from "@/hooks/useTags";
import {
  TagFilterState,
  applyTagFilter,
  clearTagFilter,
  describeTagFilter,
  isFiltering,
  renameTagInFilter,
  setIncluded,
  toggleExcluded,
  toggleIncluded,
} from "@/tagFilter";
import { Note, ViewMode } from "@/types";
import "./styles.css";

export type NotesSortBy = "relevance" | "edited" | "created";
type DateSort = "edited" | "created";

const PAGE_SIZE = 20;

interface NotesProps {
  /** Active query text; empty for image search results. */
  query: string;
  /** Ranked (and possibly refined) search results. */
  results: Note[];
  originalResults: Note[];
  refinementKeywords: string;
  isSearchLoading: boolean;
  /** True while any search (text or image) is active — the mode switch. */
  hasSearched: boolean;
  isRefined: boolean;
  onRefine: (keywords: string) => void;
  onResetRefinement: () => void;
  onClearSearch: () => void;
  /** Re-run the active search after a mutation changes note-tag membership. */
  onResultsUpdate: () => void;
  onShowRelated: (content: string) => void;
  /** Which tags the list shows and hides. Owned by App: Organize's Explore points this
   *  list at a single tag, so it cannot live here. Every transition goes through the
   *  calculations in `@/tagFilter`. */
  tagFilter: TagFilterState;
  onTagFilterChange: Dispatch<SetStateAction<TagFilterState>>;
}

export const Notes = memo(
  ({
    query,
    results,
    originalResults,
    refinementKeywords,
    isSearchLoading,
    hasSearched,
    isRefined,
    onRefine,
    onResetRefinement,
    onClearSearch,
    onResultsUpdate,
    onShowRelated,
    tagFilter,
    onTagFilterChange,
  }: NotesProps) => {
    const {
      notes: allNotes,
      isLoading: isNotesLoading,
      error,
      refetch,
    } = useAllNotes();
    const {
      tags,
      excludedTags,
      tagNotes,
      updateExcludedTags,
      removeTagFromNote,
      removeTagFromAllNotes,
      renameTag,
    } = useTags(hasSearched ? onResultsUpdate : refetch);

    const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
    const [sortBy, setSortBy] = useState<NotesSortBy>("edited");
    const [filterArchived, setFilterArchived] = useState<boolean>(false);
    const [filterPinned, setFilterPinned] = useState<boolean>(false);
    const [visibleNotesCount, setVisibleNotesCount] =
      useState<number>(PAGE_SIZE);
    const [selectedNoteIds, setSelectedNoteIds] = useState<string[]>([]);
    const [focusNoteId, setFocusNoteId] = useState<string | null>(null);
    const [showRefinement, setShowRefinement] = useState<boolean>(false);
    const [isTagDialogOpen, setIsTagDialogOpen] = useState(false);
    // Where sorting returns when a search ends: Relevance stops existing without a query.
    const lastDateSortRef = useRef<DateSort>("edited");

    const searchActive = hasSearched;
    const sourceNotes = searchActive ? results : allNotes;
    const isLoading = searchActive ? isSearchLoading : isNotesLoading;

    // Entering search mode defaults the order to relevance; leaving it restores the
    // last explicitly chosen date sort.
    useEffect(() => {
      setSortBy(searchActive ? "relevance" : lastDateSortRef.current);
      setSelectedNoteIds([]);
      setShowRefinement(false);
      setVisibleNotesCount(PAGE_SIZE);
    }, [searchActive]);

    // A new query is a new result set: paging and selection restart.
    useEffect(() => {
      setSelectedNoteIds([]);
      setVisibleNotesCount(PAGE_SIZE);
      setShowRefinement(false);
    }, [query]);

    const filteredNotes = useMemo(() => {
      let filtered = applyTagFilter(sourceNotes, tagFilter);

      if (filterArchived) {
        filtered = filtered.filter((note) => note.archived);
      }
      if (filterPinned) {
        filtered = filtered.filter((note) => note.pinned);
      }

      if (sortBy === "relevance") {
        // Relevance is the arrival order of the results; filtering preserves it.
        return filtered;
      }

      return [...filtered].sort((a, b) => {
        const dateA = new Date(sortBy === "edited" ? a.edited : a.created);
        const dateB = new Date(sortBy === "edited" ? b.edited : b.created);
        return dateB.getTime() - dateA.getTime(); // Newest first
      });
    }, [sourceNotes, sortBy, filterArchived, filterPinned, tagFilter]);

    const visibleNotes = useMemo(
      () => filteredNotes.slice(0, visibleNotesCount),
      [filteredNotes, visibleNotesCount],
    );

    const handleSelectNote = useCallback((noteId: string) => {
      setViewMode(VIEW_MODES.LIST);
      setTimeout(() => {
        const element = document.getElementById(`note-${noteId}`);
        if (element) {
          element.scrollIntoView({ behavior: "smooth", block: "center" });
          element.classList.add("highlighted-note");
          setTimeout(() => {
            element.classList.remove("highlighted-note");
          }, 2000);
        }
      }, 100);
    }, []);

    const handleViewChange = useCallback((newMode: ViewMode) => {
      setViewMode(newMode);
      if (newMode === VIEW_MODES.LIST) {
        // Cleared on the way out so picking the same note again is a fresh change
        // the 3D view can react to, rather than an unchanged prop it ignores.
        setFocusNoteId(null);
      }
    }, []);

    /** "Show connections" on a card: jump to the 3D view centred on that note. */
    const handleShowConnections = useCallback((noteId: string) => {
      setFocusNoteId(noteId);
      setViewMode(VIEW_MODES.VISUALIZATION);
    }, []);

    const handleSortChange = useCallback(
      (e: React.ChangeEvent<HTMLSelectElement>) => {
        const value = e.target.value as NotesSortBy;
        if (value !== "relevance") {
          lastDateSortRef.current = value;
        }
        setSortBy(value);
      },
      [],
    );

    const handlePinnedFilterChange = useCallback(() => {
      setFilterPinned((prev) => !prev);
    }, []);

    const handleArchivedFilterChange = useCallback(() => {
      setFilterArchived((prev) => !prev);
    }, []);

    const handleLoadMore = useCallback(() => {
      setVisibleNotesCount((prev) => prev + PAGE_SIZE);
    }, []);

    const handleTagsChange = useCallback(
      (newSelectedTags: string[]) => {
        onTagFilterChange((prev) => setIncluded(prev, newSelectedTags));
      },
      [onTagFilterChange],
    );

    /** A tag chip on a card filters in place — in both modes. Both directions reset
     *  paging: the first page of a different result set is what the user asked to see. */
    const handleIncludeTagInList = useCallback(
      (tagName: string) => {
        onTagFilterChange((prev) => toggleIncluded(prev, tagName));
        setVisibleNotesCount(PAGE_SIZE);
      },
      [onTagFilterChange],
    );

    const handleExcludeTagInList = useCallback(
      (tagName: string) => {
        onTagFilterChange((prev) => toggleExcluded(prev, tagName));
        setVisibleNotesCount(PAGE_SIZE);
      },
      [onTagFilterChange],
    );

    const handleClearFilter = useCallback(() => {
      onTagFilterChange(clearTagFilter());
      setVisibleNotesCount(PAGE_SIZE);
    }, [onTagFilterChange]);

    const handleRenameTag = useCallback(
      async (oldName: string, newName: string) => {
        await renameTag(oldName, newName);
        // Keep the filter pointing at the tag the user renamed, not at a name that no
        // longer exists.
        onTagFilterChange((prev) => renameTagInFilter(prev, oldName, newName));
      },
      [renameTag, onTagFilterChange],
    );

    const handleMergeSelectedTags = useCallback(
      async (targetTag: string) => {
        const sourceTags = tagFilter.included.filter(
          (tag) => tag !== targetTag,
        );

        for (const sourceTag of sourceTags) {
          await renameTag(sourceTag, targetTag);
        }

        onTagFilterChange((prev) => setIncluded(prev, [targetTag]));
      },
      [renameTag, tagFilter, onTagFilterChange],
    );

    const handleToggleSearchExcluded = useCallback(
      (tagName: string) => {
        const next = excludedTags.includes(tagName)
          ? excludedTags.filter((tag) => tag !== tagName)
          : [...excludedTags, tagName];
        void updateExcludedTags(next).then(() => {
          if (hasSearched) {
            onResultsUpdate();
          }
        });
      },
      [excludedTags, updateExcludedTags, hasSearched, onResultsUpdate],
    );

    const handleNoteSelection = useCallback(
      (noteId: string, isSelected: boolean) => {
        setSelectedNoteIds((prev) =>
          isSelected ? [...prev, noteId] : prev.filter((id) => id !== noteId),
        );
      },
      [],
    );

    const handleSelectAll = useCallback(() => {
      setSelectedNoteIds(filteredNotes.map((note) => note.id));
    }, [filteredNotes]);

    const handleDeselectAll = useCallback(() => {
      setSelectedNoteIds([]);
    }, []);

    const handleExportSelected = useCallback(() => {
      const selected = filteredNotes.filter((note) =>
        selectedNoteIds.includes(note.id),
      );
      exportNotes(selected, `notes-export-${todayDateStr()}.txt`);
    }, [filteredNotes, selectedNoteIds]);

    /** Export a tag's notes from the full corpus, regardless of the current mode. */
    const handleExportByTag = useCallback(
      (tagName: string) => {
        const tagNotesList = allNotes.filter(
          (note) => note.tags?.includes(tagName),
        );
        exportNotes(tagNotesList, `notes-export-${tagName}.txt`);
      },
      [allNotes],
    );

    const handleOpenTagDialog = useCallback(() => {
      if (selectedNoteIds.length > 0) {
        setIsTagDialogOpen(true);
      }
    }, [selectedNoteIds]);

    const handleCloseTagDialog = useCallback(() => {
      setIsTagDialogOpen(false);
    }, []);

    const handleTagConfirm = useCallback(
      async (tagName: string) => {
        try {
          await tagNotes(selectedNoteIds, tagName);
          setIsTagDialogOpen(false);
          setSelectedNoteIds([]);
          if (hasSearched) {
            onResultsUpdate();
          }
        } catch (err) {
          console.error("Failed to tag notes:", err);
        }
      },
      [selectedNoteIds, tagNotes, hasSearched, onResultsUpdate],
    );

    const toggleRefinement = useCallback(() => {
      setShowRefinement((prev) => !prev);
      // Toggling refinement off also resets any applied refinement.
      if (showRefinement && refinementKeywords) {
        onResetRefinement();
      }
    }, [showRefinement, refinementKeywords, onResetRefinement]);

    useEffect(() => {
      const handleScroll = () => {
        if (
          window.innerHeight + document.documentElement.scrollTop >=
          document.documentElement.offsetHeight - 100
        ) {
          handleLoadMore();
        }
      };

      window.addEventListener("scroll", handleScroll);
      return () => window.removeEventListener("scroll", handleScroll);
    }, [handleLoadMore]);

    if (isLoading) {
      return (
        <div className="all-notes-container">
          {/* layout=list ensures the skeleton matches the vertical list that will
              be rendered once data arrives */}
          <NoteSkeleton count={12} layout="list" />
        </div>
      );
    }

    if (!searchActive && error) {
      return <div className="all-notes-error">Error: {error}</div>;
    }

    return (
      <div className="all-notes-container">
        {tags.length > 0 && (
          <TagFilter
            tags={tags}
            filter={tagFilter}
            onUpdateSelectedTags={handleTagsChange}
            onToggleExcluded={handleExcludeTagInList}
            onClearFilter={handleClearFilter}
            onRenameTag={handleRenameTag}
            onMergeTags={handleMergeSelectedTags}
            onExportTag={handleExportByTag}
            searchExcludedTags={excludedTags}
            onToggleSearchExcluded={handleToggleSearchExcluded}
            onDeleteTagEverywhere={removeTagFromAllNotes}
          />
        )}

        {showRefinement && searchActive && originalResults.length > 0 && (
          <RefinementSearchBar onRefine={onRefine} isVisible={true} />
        )}

        <div className="all-notes-header">
          <div className="all-notes-count">
            {searchActive && filteredNotes.length === 0 ? (
              <span id="no-results">No matching notes found.</span>
            ) : (
              <>
                {searchActive ? "Found " : ""}
                {filteredNotes.length} note{filteredNotes.length === 1
                  ? ""
                  : "s"}
                {isFiltering(tagFilter) && (
                  <span className="tag-filter-status">
                    {" "}
                    ({describeTagFilter(tagFilter)})
                  </span>
                )}
                {isRefined && <span className="refined-filter-info"> (filtered by: {refinementKeywords})</span>}
              </>
            )}
            {searchActive && (
              <button
                className="clear-search-button"
                onClick={onClearSearch}
                title="Clear the search and browse all notes"
                aria-label="Clear search"
              >
                <span className="material-icons">close</span>
                <span>Clear search</span>
              </button>
            )}
          </div>

          <div className="all-notes-controls">
            {viewMode === VIEW_MODES.LIST && filteredNotes.length > 0 && (
              <div className="selection-controls">
                <button
                  className="selection-toggle-button"
                  onClick={
                    selectedNoteIds.length === 0
                      ? handleSelectAll
                      : handleDeselectAll
                  }
                  title={
                    selectedNoteIds.length === 0
                      ? "Select all notes"
                      : "Deselect all notes"
                  }
                >
                  <span className="material-icons">
                    {selectedNoteIds.length === 0
                      ? "check_box_outline_blank"
                      : "check_box"}
                  </span>
                  <span>
                    {selectedNoteIds.length === 0
                      ? "Select All"
                      : "Deselect All"}
                  </span>
                </button>

                {selectedNoteIds.length > 0 && (
                  <button
                    className="tag-button"
                    onClick={handleOpenTagDialog}
                    title={`Tag ${selectedNoteIds.length} selected notes`}
                  >
                    <span className="material-icons">label</span>
                    <span>Tag ({selectedNoteIds.length})</span>
                  </button>
                )}

                {selectedNoteIds.length > 0 && (
                  <button
                    className="tag-button"
                    onClick={handleExportSelected}
                    title={`Export ${selectedNoteIds.length} selected notes`}
                  >
                    <span className="material-icons">download</span>
                    <span>Export ({selectedNoteIds.length})</span>
                  </button>
                )}
              </div>
            )}

            {searchActive && originalResults.length > 0 && (
              <button
                className={`refinement-toggle-button ${
                  showRefinement ? "active" : ""
                }`}
                onClick={toggleRefinement}
                title={
                  showRefinement
                    ? "Hide refinement search"
                    : "Refine search results"
                }
              >
                <span className="material-icons">filter_list</span>
                <span>Refine</span>
              </button>
            )}

            {viewMode === VIEW_MODES.LIST && (
              <div className="all-notes-filters">
                <select
                  value={sortBy}
                  onChange={handleSortChange}
                  className="all-notes-select"
                >
                  {searchActive && (
                    <option value="relevance">Sort by Relevance</option>
                  )}
                  <option value="edited">Sort by Last Edited</option>
                  <option value="created">Sort by Created Date</option>
                </select>

                <label className="filter-checkbox">
                  <input
                    type="checkbox"
                    checked={filterPinned}
                    onChange={handlePinnedFilterChange}
                  />
                  Pinned Only
                </label>

                <label className="filter-checkbox">
                  <input
                    type="checkbox"
                    checked={filterArchived}
                    onChange={handleArchivedFilterChange}
                  />
                  Archived Only
                </label>
              </div>
            )}

            <ViewToggle currentView={viewMode} onChange={handleViewChange} />
          </div>
        </div>

        {viewMode === VIEW_MODES.LIST ? (
          <div className="all-notes-list">
            {visibleNotes.length === 0
              ? !searchActive && (
                  <div className="all-notes-empty">
                    No notes to display with current filters
                  </div>
                )
              : visibleNotes.map((note) => (
                  <div id={`note-${note.id}`} key={note.id}>
                    <NoteCard
                      note={note}
                      query={searchActive ? query : ""}
                      refinementKeywords={
                        searchActive ? refinementKeywords : undefined
                      }
                      isSelectable={true}
                      isSelected={selectedNoteIds.includes(note.id)}
                      onShowRelated={onShowRelated}
                      onShowConnections={handleShowConnections}
                      onSelectNote={handleNoteSelection}
                      onRemoveTag={removeTagFromNote}
                      onRenameTag={renameTag}
                      onTagClick={handleIncludeTagInList}
                      onTagExclude={handleExcludeTagInList}
                      tagFilter={tagFilter}
                    />
                  </div>
                ))}
          </div>
        ) : (
          <div className="all-notes-visualization">
            {/* filteredNotes, not visibleNotes: `visibleNotes` is the card list's
                infinite-scroll window (20 at a time, grown by a scroll listener that
                never fires here because the list is not rendered in this mode). The
                3D view filters by what it is given, so handing it the paged slice
                showed a 20-point cloud. Tag/pinned/archived filters still apply —
                they are baked into filteredNotes. */}
            <Visualization
              searchResults={filteredNotes}
              onSelectNote={handleSelectNote}
              isAllNotesView={!searchActive}
              focusNoteId={focusNoteId}
            />
          </div>
        )}

        <TagDialog
          isOpen={isTagDialogOpen}
          selectedNoteIds={selectedNoteIds}
          existingTags={tags}
          onClose={handleCloseTagDialog}
          onConfirm={handleTagConfirm}
        />

        <ScrollToTop threshold={200} />
      </div>
    );
  },
);
```

Notes on two details an implementer might otherwise "fix":

- `useTags(hasSearched ? onResultsUpdate : refetch)`: the `onNotesChanged` escape hatch re-runs _uncached_ side effects. In search mode that is re-POSTing the query (App's `handleResultsUpdate`); in browse mode the cached all-notes read refreshes via invalidation, so `refetch` is belt-and-braces and matches AllNotes' current wiring.
- `NoteCard`'s `refinementKeywords` and `tagFilter` props are both optional in `NoteCard`'s own interface — verify with `grep -n "refinementKeywords\|tagFilter" client/src/components/NoteCard.tsx` before assuming; if `tagFilter` is not a NoteCard prop, drop that line (AllNotes passes it today, Results does not).

- [ ] **Step 5: Run the tests**

Run: `cd client && npx vitest run src/components/__tests__/Notes.test.tsx`
Expected: PASS (all browse, search, and ported tag-merge cases)

- [ ] **Step 6: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: clean (Notes is not yet imported anywhere — that's Task 5)

- [ ] **Step 7: Commit**

```bash
git add client/src/components/Notes/ client/src/components/__tests__/Notes.test.tsx
git commit -m "feat(notes): add the unified Notes component with one filter/sort pipeline"
```

---

### Task 5: Wire the app to the merged tab; delete the old components

**Files:**

- Modify: `client/src/components/TabNavigation/index.tsx`
- Modify: `client/src/App.tsx`
- Modify: `client/src/components/ImageGallery/GalleryContext.tsx:115`
- Delete: `client/src/components/Results.tsx`
- Delete: `client/src/components/AllNotes/` (both files)
- Delete: `client/src/components/TagManager/` (both files)
- Delete: `client/src/components/__tests__/AllNotes.test.tsx`

**Interfaces:**

- Consumes: `Notes` (Task 4), `clearSearch` (Task 1), `SearchBar.onClear` (Task 2).
- Produces: `TabId = 'notes' | 'chat' | 'organize'` — Organize (`onExploreTag` flows) and the gallery keep working against `'notes'`.

- [ ] **Step 1: Update `TabNavigation`**

In `client/src/components/TabNavigation/index.tsx`:

```ts
export type TabId = "notes" | "chat" | "organize";
```

and replace the first two `TABS` entries with one:

```ts
  {
    id: 'notes',
    label: 'Notes',
    icon: 'notes',
  },
```

- [ ] **Step 2: Update `App.tsx`**

- Imports: remove `AllNotes`, `Results`; add `Notes`:

```ts
import { Notes } from "@/components/Notes";
```

- `useSearch()` destructuring: add `clearSearch`.
- `useState<TabId>('search')` → `useState<TabId>('notes')`.
- `handleSearch`: `setActiveTab('search')` → `setActiveTab('notes')`.
- `handleExploreTag`: `setActiveTab('all-notes')` → `setActiveTab('notes')` (keep the rest — Organize's Explore still navigates here).
- Every `activeTab === 'search'` guard around `SearchModeToggle` / `SearchBar` / `ImageSearchUpload` becomes `activeTab === 'notes'`.
- `SearchBar` gains the clear prop: `<SearchBar onSearch={handleSearch} onClear={clearSearch} currentQuery={query} />`.
- Replace the two tab blocks (`activeTab === 'search' && <Results …>` and `activeTab === 'all-notes' && <AllNotes …>`) with one:

```tsx
{
  activeTab === "notes" && (
    <ErrorBoundary fallbackLabel="Notes">
      <Notes
        query={query}
        results={results}
        originalResults={originalResults}
        refinementKeywords={refinementKeywords}
        isSearchLoading={isLoading}
        hasSearched={hasSearched}
        isRefined={isRefined}
        onRefine={handleRefinement}
        onResetRefinement={resetRefinement}
        onClearSearch={clearSearch}
        onResultsUpdate={handleResultsUpdate}
        onShowRelated={handleSearch}
        tagFilter={tagFilter}
        onTagFilterChange={setTagFilter}
      />
    </ErrorBoundary>
  );
}
```

- [ ] **Step 3: Update the gallery's tab switch**

In `client/src/components/ImageGallery/GalleryContext.tsx` line ~115: `onSwitchTab('search')` → `onSwitchTab('notes')`.

- [ ] **Step 4: Delete the replaced components and their test**

```bash
git rm client/src/components/Results.tsx
git rm -r client/src/components/AllNotes client/src/components/TagManager
git rm client/src/components/__tests__/AllNotes.test.tsx
```

- [ ] **Step 5: Sweep for dangling references**

Run: `cd client && grep -rn "AllNotes\|TagManager\|Results\b\|'all-notes'\|'search'" src --include="*.tsx" --include="*.ts" | grep -vE "useAllNotes|ALL_NOTES|all-notes-|searchResults|SearchBar|search_|'search-|performSearch|hasSearched|isSearchLoading|onSearch|search-container|TagManagerDashboard"`
Expected: no hits pointing at the deleted components or dead tab ids. `hooks/useAllNotes.ts`, the `all-notes-*` CSS class names, and Organize's `TagManagerDashboard` (an unrelated component) all stay.

Note: `App.css` and `index.css` may hold `.results-container` / `.tag-manager` rules that are now dead. Check with `grep -n "results-container\|results-header\|results-list\|tag-manager" client/src/App.css client/src/index.css client/src/components/TagManager/styles.css 2>/dev/null` — delete rules that only the deleted components used, keep anything shared (e.g. `#no-results`, `refined-filter-info`, `refinement-toggle-button` are still used by `Notes`; move them into `Notes/styles.css` if they lived in `TagManager/styles.css`).

- [ ] **Step 6: Run the whole frontend suite, types, lint, build**

Run: `cd client && npx vitest run && npx tsc --noEmit && npm run lint && npm run build`
Expected: all green. If a test outside the touched files references `'search'`/`'all-notes'` tab ids, update it to `'notes'`.

- [ ] **Step 7: Commit**

```bash
git add -A client/src
git commit -m "feat(notes): merge the Search and All Notes tabs into one Notes tab"
```

---

### Task 6: End-to-end sanity pass in the running app

Automated tests mock NoteCard/Visualization; one manual pass catches wiring the mocks hide. **Do not read note contents while doing this — verify structurally (counts, ordering, controls) only.**

**Files:** none (verification only).

- [ ] **Step 1: Start the dev environment**

Run: `make dev` (or the project's documented equivalent) and open the client.

- [ ] **Step 2: Walk the merged tab**

- Notes tab opens showing all notes, newest-edited first; sort dropdown has no Relevance option.
- Type a query, search: result count line appears, sort reads Relevance, Refine and Clear search appear.
- Switch sort to Last Edited — order changes; back to Relevance — original ranking returns.
- Open Filter by Tags: include a tag → results narrow; the search-off icon toggles a tag's search-wide exclusion; the trash icon prompts before deleting.
- Select two notes → Tag and Export buttons appear; bulk-tag round-trips.
- Toggle 3D view in both modes; "show connections" on a card focuses the 3D view.
- Clear search (both the ✕ in the bar and the chip by the count) → browse view returns with prior date sort.
- Organize tab → Explore on a tag → lands on Notes filtered to that tag.
- If image search is enabled: image mode returns results into the same list; gallery "find similar" switches to the Notes tab.

- [ ] **Step 3: Report**

Report any mismatch against the spec (`docs/superpowers/specs/2026-07-30-notes-tab-merge-design.md`) back to the user before calling the work done — with the superpowers:verification-before-completion skill's evidence standard.
