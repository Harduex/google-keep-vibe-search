import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AllNotes } from '@/components/AllNotes';
import { useAllNotes } from '@/hooks/useAllNotes';
import { useTags } from '@/hooks/useTags';
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
    });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('shows merge only after selecting more than one tag', async () => {
    const user = userEvent.setup();
    render(<AllNotes onShowRelated={vi.fn()} />);

    await user.click(screen.getByText('Filter by Tags'));

    expect(screen.queryByRole('button', { name: 'Merge Selected' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: /work/i }));

    expect(screen.queryByRole('button', { name: 'Merge Selected' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: /ideas/i }));

    expect(screen.getByRole('button', { name: 'Merge Selected' })).toBeInTheDocument();
  });

  it('merges selected tags into the chosen selected target', async () => {
    const user = userEvent.setup();
    render(<AllNotes onShowRelated={vi.fn()} />);

    await user.click(screen.getByText('Filter by Tags'));
    await user.click(screen.getByRole('checkbox', { name: /work/i }));
    await user.click(screen.getByRole('checkbox', { name: /ideas/i }));
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
      expect(screen.getByText('(1 selected)')).toBeInTheDocument();
    });

    expect(screen.getByRole('checkbox', { name: /work/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /ideas/i })).not.toBeChecked();
  });
});
