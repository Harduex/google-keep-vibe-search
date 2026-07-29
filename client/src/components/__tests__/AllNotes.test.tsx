import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AllNotes } from '@/components/AllNotes';
import { useAllNotes } from '@/hooks/useAllNotes';
import { useTags } from '@/hooks/useTags';
import { EMPTY_TAG_FILTER } from '@/tagFilter';
import { Note, Tag } from '@/types';

vi.mock('@/hooks/useAllNotes');
vi.mock('@/hooks/useTags');

vi.mock('@/components/NoteCard', () => ({
  NoteCard: () => <div data-testid="note-card" />,
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

const mockUseAllNotes = vi.mocked(useAllNotes);
const mockUseTags = vi.mocked(useTags);

const tags: Tag[] = [
  { name: 'Work', count: 3 },
  { name: 'Ideas', count: 2 },
  { name: 'Travel', count: 1 },
];

const notes: Note[] = [
  {
    id: '1',
    title: 'First',
    content: 'Alpha',
    created: '2025-01-01T00:00:00Z',
    edited: '2025-01-02T00:00:00Z',
    archived: false,
    pinned: false,
    color: 'DEFAULT',
    score: 0,
    tags: ['Work'],
  },
  {
    id: '2',
    title: 'Second',
    content: 'Beta',
    created: '2025-01-03T00:00:00Z',
    edited: '2025-01-04T00:00:00Z',
    archived: false,
    pinned: false,
    color: 'DEFAULT',
    score: 0,
    tags: ['Ideas'],
  },
];

/** Row controls in the filter panel: one segmented show/hide pair per tag. */
const showOnly = (tagName: string) =>
  screen.getByRole('button', { name: `Show only notes tagged "${tagName}"` });
const hide = (tagName: string) =>
  screen.getByRole('button', { name: `Hide notes tagged "${tagName}"` });

/** The include filter is owned by App, so a test needs a state owner of its own. */
const StatefulAllNotes = () => {
  const [tagFilter, setTagFilter] = useState(EMPTY_TAG_FILTER);
  return (
    <AllNotes onShowRelated={vi.fn()} tagFilter={tagFilter} onTagFilterChange={setTagFilter} />
  );
};

describe('AllNotes tag merge from filter', () => {
  const renameTag = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAllNotes.mockReturnValue({
      notes,
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
      renameTag,
      refetchTags: vi.fn(),
      refetchExcludedTags: vi.fn(),
      coverage: null,
      isCoverageLoading: false,
    });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('shows merge only after selecting more than one tag', async () => {
    const user = userEvent.setup();
    render(<StatefulAllNotes />);

    await user.click(screen.getByText('Filter by Tags'));

    expect(screen.queryByRole('button', { name: 'Merge Selected' })).not.toBeInTheDocument();

    await user.click(showOnly('Work'));

    expect(screen.queryByRole('button', { name: 'Merge Selected' })).not.toBeInTheDocument();

    await user.click(showOnly('Ideas'));

    expect(screen.getByRole('button', { name: 'Merge Selected' })).toBeInTheDocument();
  });

  it('merges selected tags into the chosen selected target', async () => {
    const user = userEvent.setup();
    render(<StatefulAllNotes />);

    await user.click(screen.getByText('Filter by Tags'));
    await user.click(showOnly('Work'));
    await user.click(showOnly('Ideas'));
    await user.click(screen.getByRole('button', { name: 'Merge Selected' }));

    expect(screen.getByText('Keep this tag:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Work' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ideas' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Travel' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Work' }));

    await waitFor(() => {
      expect(renameTag).toHaveBeenCalledWith('Ideas', 'Work');
    });

    expect(renameTag).toHaveBeenCalledTimes(1);
    expect(window.confirm).toHaveBeenCalledWith(
      'Merge Ideas into "Work"? All notes with the other selected tags will use "Work" instead.',
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Stop showing only "Work"' })).toBeInTheDocument();
    });

    expect(showOnly('Work')).toHaveAttribute('aria-pressed', 'true');
    expect(showOnly('Ideas')).toHaveAttribute('aria-pressed', 'false');
  });

  it('excluding a tag hides its notes and clears any selection of it', async () => {
    const user = userEvent.setup();
    render(<StatefulAllNotes />);

    await user.click(screen.getByText('Filter by Tags'));
    await user.click(showOnly('Work'));
    expect(screen.getByRole('button', { name: 'Stop showing only "Work"' })).toBeInTheDocument();

    await user.click(hide('Work'));

    // The include of the same tag is dropped: holding both would hide the very notes the
    // include asked for.
    expect(showOnly('Work')).toHaveAttribute('aria-pressed', 'false');
    expect(
      screen.queryByRole('button', { name: 'Stop showing only "Work"' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop hiding "Work"' })).toBeInTheDocument();
    // Note 1 is tagged Work and is now hidden; note 2 (Ideas) remains.
    expect(screen.getAllByTestId('note-card')).toHaveLength(1);
  });

  it('makes the filter panel sticky only while a filter is applied', async () => {
    const user = userEvent.setup();
    const { container } = render(<StatefulAllNotes />);

    expect(container.querySelector('.tag-filter')).not.toHaveClass('sticky');

    await user.click(screen.getByText('Filter by Tags'));
    await user.click(showOnly('Work'));

    expect(container.querySelector('.tag-filter')).toHaveClass('sticky');

    await user.click(showOnly('Work'));

    expect(container.querySelector('.tag-filter')).not.toHaveClass('sticky');
  });
});
