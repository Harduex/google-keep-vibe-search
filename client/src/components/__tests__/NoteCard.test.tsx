import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { NoteCard } from '@/components/NoteCard';
import { EMPTY_TAG_FILTER } from '@/tagFilter';
import { Note } from '@/types';

vi.mock('@/components/ImageGallery', () => ({
  default: () => null,
}));

vi.mock('@/components/NoteContent', () => ({
  NoteContent: () => <div data-testid="note-content" />,
}));

const note: Note = {
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
};

describe('NoteCard tag filter controls', () => {
  it('offers include and exclude per tag, reporting the tag to each handler', async () => {
    const user = userEvent.setup();
    const onTagClick = vi.fn();
    const onTagExclude = vi.fn();

    render(
      <NoteCard
        note={note}
        query=""
        onShowRelated={vi.fn()}
        onTagClick={onTagClick}
        onTagExclude={onTagExclude}
        tagFilter={EMPTY_TAG_FILTER}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Include tag Work' }));
    expect(onTagClick).toHaveBeenCalledWith('Work');

    await user.click(screen.getByRole('button', { name: 'Exclude tag Work' }));
    expect(onTagExclude).toHaveBeenCalledWith('Work');
  });

  it('flips both controls to their "stop" wording once the tag is filtered', () => {
    const { rerender } = render(
      <NoteCard
        note={note}
        query=""
        onShowRelated={vi.fn()}
        onTagClick={vi.fn()}
        onTagExclude={vi.fn()}
        tagFilter={{ included: ['Work'], excluded: [] }}
      />,
    );

    expect(screen.getByRole('button', { name: 'Stop including tag Work' })).toBeInTheDocument();
    expect(document.querySelector('.badge-tag')).toHaveClass('filtering');

    rerender(
      <NoteCard
        note={note}
        query=""
        onShowRelated={vi.fn()}
        onTagClick={vi.fn()}
        onTagExclude={vi.fn()}
        tagFilter={{ included: [], excluded: ['Work'] }}
      />,
    );

    expect(screen.getByRole('button', { name: 'Stop excluding tag Work' })).toBeInTheDocument();
    expect(document.querySelector('.badge-tag')).toHaveClass('excluding');
  });

  it('leaves the chip inert when no filter handlers are given', () => {
    render(<NoteCard note={note} query="" onShowRelated={vi.fn()} />);

    expect(screen.queryByRole('button', { name: /tag Work/ })).not.toBeInTheDocument();
    expect(screen.getByText('Work')).toBeInTheDocument();
  });
});
