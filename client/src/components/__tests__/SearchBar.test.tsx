import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SearchBar } from '@/components/SearchBar';

describe('SearchBar clear button', () => {
  it('is absent when the input is empty', () => {
    render(<SearchBar onSearch={vi.fn()} onClear={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument();
  });

  it('clears the input and notifies the owner', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(<SearchBar onSearch={vi.fn()} onClear={onClear} currentQuery="groceries" />);

    await user.click(screen.getByRole('button', { name: 'Clear search' }));

    expect(onClear).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText(/Search your notes/)).toHaveValue('');
  });
});
