import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LoadingScreen } from '../LoadingScreen';

describe('LoadingScreen', () => {
  it('renders a fullscreen overlay with three bouncing dots and a friendly message', () => {
    render(<LoadingScreen />);
    const overlay = screen.getByTestId('loading-screen');
    expect(overlay).toBeInTheDocument();

    // confirm the dot loader structure
    const dots = overlay.querySelectorAll('.loader-dots .dot');
    expect(dots.length).toBe(3);

    // message and branding
    expect(screen.getByText(/Preparing your search/i)).toBeInTheDocument();
    expect(screen.getByText('Google Keep Vibe Search')).toBeInTheDocument();
  });

  it('displays provided message when given', () => {
    const custom = 'almost done…';
    render(<LoadingScreen message={custom} />);
    expect(screen.getByText(custom)).toBeInTheDocument();
  });
});
