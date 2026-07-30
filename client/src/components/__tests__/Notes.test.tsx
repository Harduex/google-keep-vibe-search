import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Notes } from '@/components/Notes';
import { useAllNotes } from '@/hooks/useAllNotes';
import { useTags } from '@/hooks/useTags';
import { EMPTY_TAG_FILTER } from '@/tagFilter';
import { Note, Tag } from '@/types';

vi.mock('@/hooks/useAllNotes');
vi.mock('@/hooks/useTags');

vi.mock('@/components/NoteCard', () => ({
  NoteCard: ({ note }: { note: Note }) => <div data-testid="note-card">{note.title}</div>,
}));

vi.mock('@/components/NoteSkeleton', () => ({
  NoteSkeleton: () => <div data-testid="note-skeleton" />,
}));

vi.mock('@/components/ScrollToTop', () => ({
  ScrollToTop: () => null,
}));

vi.mock('@/components/ViewToggle', () => ({
  ViewToggle: () => <div data-testid="view-toggle" />,
}));

vi.mock('@/components/Visualization', () => ({
  Visualization: () => <div data-testid="visualization" />,
}));

vi.mock('@/components/RefinementSearchBar', () => ({
  RefinementSearchBar: () => <div data-testid="refinement-bar" />,
}));

const mockUseAllNotes = vi.mocked(useAllNotes);
const mockUseTags = vi.mocked(useTags);

const tags: Tag[] = [
  { name: 'Work', count: 3 },
  { name: 'Ideas', count: 2 },
  { name: 'Travel', count: 1 },
];

const makeNote = (overrides: Partial<Note>): Note => ({
  id: 'x',
  title: 'Untitled',
  content: '',
  created: '2025-01-01T00:00:00Z',
  edited: '2025-01-02T00:00:00Z',
  archived: false,
  pinned: false,
  color: 'DEFAULT',
  score: 0,
  tags: [],
  ...overrides,
});

const allNotes: Note[] = [
  makeNote({
    id: '1',
    title: 'First',
    tags: ['Work'],
    edited: '2025-01-02T00:00:00Z',
  }),
  makeNote({
    id: '2',
    title: 'Second',
    tags: ['Ideas'],
    edited: '2025-01-04T00:00:00Z',
  }),
  makeNote({
    id: '3',
    title: 'Third',
    tags: ['Travel'],
    edited: '2025-01-06T00:00:00Z',
  }),
];

// Relevance order deliberately disagrees with date order: '1' (older) ranks first.
const searchResults: Note[] = [
  makeNote({
    id: '1',
    title: 'First',
    tags: ['Work'],
    score: 0.9,
    edited: '2025-01-02T00:00:00Z',
  }),
  makeNote({
    id: '3',
    title: 'Third',
    tags: ['Travel'],
    score: 0.4,
    edited: '2025-01-06T00:00:00Z',
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
  query = '',
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
  screen.getByRole('button', { name: `Show only notes tagged "${tagName}"` });
const hide = (tagName: string) =>
  screen.getByRole('button', { name: `Hide notes tagged "${tagName}"` });

describe('Notes', () => {
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
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  describe('browse mode (no active search)', () => {
    it('shows the full corpus sorted by last edited, without a Relevance option', () => {
      render(<StatefulNotes />);

      const cards = screen.getAllByTestId('note-card');
      expect(cards.map((c) => c.textContent)).toEqual(['Third', 'Second', 'First']);
      expect(screen.queryByRole('option', { name: 'Sort by Relevance' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Refine/ })).not.toBeInTheDocument();
    });
  });

  describe('search mode', () => {
    it('shows results in relevance order by default, with a Relevance sort option', () => {
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      const cards = screen.getAllByTestId('note-card');
      expect(cards.map((c) => c.textContent)).toEqual(['First', 'Third']);

      const sortSelect = screen.getByRole('combobox');
      expect(sortSelect).toHaveValue('relevance');
      expect(screen.getByRole('option', { name: 'Sort by Relevance' })).toBeInTheDocument();
    });

    it('can re-sort search results by date', async () => {
      const user = userEvent.setup();
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      await user.selectOptions(screen.getByRole('combobox'), 'edited');

      const cards = screen.getAllByTestId('note-card');
      expect(cards.map((c) => c.textContent)).toEqual(['Third', 'First']);
    });

    it('applies the tag view filter on top of search results', async () => {
      const user = userEvent.setup();
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      await user.click(screen.getByText('Filter by Tags'));
      await user.click(showOnly('Work'));

      const cards = screen.getAllByTestId('note-card');
      expect(cards.map((c) => c.textContent)).toEqual(['First']);
    });

    it('offers Refine and Clear search only while searching', () => {
      render(<StatefulNotes hasSearched results={searchResults} query="q" />);

      expect(screen.getByRole('button', { name: /Refine/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Clear search' })).toBeInTheDocument();
    });

    it('clearing the search hands control back to the owner', async () => {
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

      await user.click(screen.getByRole('button', { name: 'Clear search' }));
      expect(onClearSearch).toHaveBeenCalledTimes(1);
    });

    it('shows the search empty state when results are empty', () => {
      render(<StatefulNotes hasSearched results={[]} query="q" />);
      expect(screen.getByText('No matching notes found.')).toBeInTheDocument();
    });
  });

  // Ported from AllNotes.test.tsx — the merge must not regress tag-filter behavior.
  describe('tag merge from filter', () => {
    it('shows merge only after selecting more than one tag', async () => {
      const user = userEvent.setup();
      render(<StatefulNotes />);

      await user.click(screen.getByText('Filter by Tags'));
      expect(screen.queryByRole('button', { name: 'Merge Selected' })).not.toBeInTheDocument();

      await user.click(showOnly('Work'));
      expect(screen.queryByRole('button', { name: 'Merge Selected' })).not.toBeInTheDocument();

      await user.click(showOnly('Ideas'));
      expect(screen.getByRole('button', { name: 'Merge Selected' })).toBeInTheDocument();
    });

    it('merges selected tags into the chosen selected target', async () => {
      const user = userEvent.setup();
      render(<StatefulNotes />);

      await user.click(screen.getByText('Filter by Tags'));
      await user.click(showOnly('Work'));
      await user.click(showOnly('Ideas'));
      await user.click(screen.getByRole('button', { name: 'Merge Selected' }));

      expect(screen.getByText('Keep this tag:')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Work' }));

      await waitFor(() => {
        expect(renameTag).toHaveBeenCalledWith('Ideas', 'Work');
      });
      expect(renameTag).toHaveBeenCalledTimes(1);
    });

    it('excluding a tag hides its notes and clears any selection of it', async () => {
      const user = userEvent.setup();
      render(<StatefulNotes />);

      await user.click(screen.getByText('Filter by Tags'));
      await user.click(showOnly('Work'));
      await user.click(hide('Work'));

      expect(showOnly('Work')).toHaveAttribute('aria-pressed', 'false');
      expect(screen.getByRole('button', { name: 'Stop hiding "Work"' })).toBeInTheDocument();
      expect(screen.getAllByTestId('note-card')).toHaveLength(2);
    });

    it('makes the filter panel sticky only while a filter is applied', async () => {
      const user = userEvent.setup();
      const { container } = render(<StatefulNotes />);

      expect(container.querySelector('.tag-filter')).not.toHaveClass('sticky');

      await user.click(screen.getByText('Filter by Tags'));
      await user.click(showOnly('Work'));
      expect(container.querySelector('.tag-filter')).toHaveClass('sticky');

      await user.click(showOnly('Work'));
      expect(container.querySelector('.tag-filter')).not.toHaveClass('sticky');
    });
  });
});
