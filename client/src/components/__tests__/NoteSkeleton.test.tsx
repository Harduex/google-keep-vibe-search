import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { NoteSkeleton } from '../NoteSkeleton';

describe('NoteSkeleton', () => {
  it('renders default 6 skeleton cards', () => {
    render(<NoteSkeleton />);
    const cards = document.querySelectorAll('.skeleton-card');
    expect(cards.length).toBe(6);
  });

  it('renders specified number of skeleton cards', () => {
    render(<NoteSkeleton count={3} />);
    const cards = document.querySelectorAll('.skeleton-card');
    expect(cards.length).toBe(3);
  });

  it('renders skeleton lines within each card', () => {
    render(<NoteSkeleton count={1} />);
    const card = document.querySelector('.skeleton-card');
    expect(card).toBeInTheDocument();
    expect(card?.querySelectorAll('.skeleton-line').length).toBeGreaterThan(0);
  });
});
