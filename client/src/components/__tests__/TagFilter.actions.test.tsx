import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TagFilter } from '@/components/TagFilter';
import { EMPTY_TAG_FILTER } from '@/tagFilter';
import { Tag } from '@/types';

const tags: Tag[] = [
  { name: 'Work', count: 3 },
  { name: 'Ideas', count: 2 },
];

const baseProps = {
  tags,
  filter: EMPTY_TAG_FILTER,
  onUpdateSelectedTags: vi.fn(),
  onToggleExcluded: vi.fn(),
  onClearFilter: vi.fn(),
};

describe('TagFilter search-wide actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('toggles a tag in and out of the search-wide excluded set', async () => {
    const user = userEvent.setup();
    const onToggleSearchExcluded = vi.fn();
    render(
      <TagFilter
        {...baseProps}
        searchExcludedTags={['Ideas']}
        onToggleSearchExcluded={onToggleSearchExcluded}
      />,
    );

    await user.click(screen.getByText('Filter by Tags'));

    // An already-excluded tag reads as such and offers re-inclusion.
    const ideasButton = screen.getByRole('button', {
      name: 'Include "Ideas" in search results again',
    });
    expect(ideasButton).toHaveAttribute('aria-pressed', 'true');

    await user.click(
      screen.getByRole('button', {
        name: 'Exclude "Work" from search results',
      }),
    );
    expect(onToggleSearchExcluded).toHaveBeenCalledWith('Work');
  });

  it('confirms before deleting a tag everywhere', async () => {
    const user = userEvent.setup();
    const onDeleteTagEverywhere = vi.fn();
    render(<TagFilter {...baseProps} onDeleteTagEverywhere={onDeleteTagEverywhere} />);

    await user.click(screen.getByText('Filter by Tags'));
    await user.click(screen.getByRole('button', { name: 'Delete tag "Work" from all notes' }));

    expect(window.confirm).toHaveBeenCalledWith(
      'Are you sure you want to remove the tag "Work" from all notes?',
    );
    expect(onDeleteTagEverywhere).toHaveBeenCalledWith('Work');
  });

  it('does not delete when the confirm is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();
    const onDeleteTagEverywhere = vi.fn();
    render(<TagFilter {...baseProps} onDeleteTagEverywhere={onDeleteTagEverywhere} />);

    await user.click(screen.getByText('Filter by Tags'));
    await user.click(screen.getByRole('button', { name: 'Delete tag "Work" from all notes' }));

    expect(onDeleteTagEverywhere).not.toHaveBeenCalled();
  });
});
