import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TagManagementCard } from '@/components/Organize/TagManagementCard';
import { Tag } from '@/types';

const tag: Tag = { name: 'Work', count: 3 };
const allTags: Tag[] = [tag, { name: 'Ideas', count: 2 }];

const baseProps = {
  tag,
  allTags,
  onRename: vi.fn(),
  onMerge: vi.fn(),
  onRemove: vi.fn(),
  onExplore: vi.fn(),
};

describe('TagManagementCard app-wide exclusion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers to hide an included tag everywhere', async () => {
    const user = userEvent.setup();
    const onToggleExcluded = vi.fn();
    render(
      <TagManagementCard {...baseProps} isExcluded={false} onToggleExcluded={onToggleExcluded} />,
    );

    const button = screen.getByRole('button', { name: 'Hide "Work" notes everywhere' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByText('hidden')).not.toBeInTheDocument();

    await user.click(button);
    expect(onToggleExcluded).toHaveBeenCalledWith('Work');
  });

  it('marks an excluded tag and offers re-inclusion', async () => {
    const user = userEvent.setup();
    const onToggleExcluded = vi.fn();
    render(
      <TagManagementCard {...baseProps} isExcluded={true} onToggleExcluded={onToggleExcluded} />,
    );

    const button = screen.getByRole('button', { name: 'Show "Work" notes again' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('hidden')).toBeInTheDocument();

    await user.click(button);
    expect(onToggleExcluded).toHaveBeenCalledWith('Work');
  });
});
