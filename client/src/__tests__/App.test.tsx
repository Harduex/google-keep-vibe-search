import { render, screen } from '@testing-library/react';
import { describe, it, vi } from 'vitest';

// we import the whole module so we can spy on individual hooks
import * as backendHook from '@/hooks/useBackendReady';
import * as statsHook from '@/hooks/useStats';

import App from '../App';

describe('App loading behavior', () => {
  it('shows loading screen while backend is not yet ready', () => {
    vi.spyOn(backendHook, 'useBackendReady').mockReturnValue({ ready: false, error: null });
    // stats hook should not matter since we never render past loading
    vi.spyOn(statsHook, 'useStats').mockReturnValue({
      stats: null,
      isLoading: false,
      error: null,
      refetchStats: vi.fn(),
    });

    render(<App />);
    expect(screen.getByTestId('loading-screen')).toBeInTheDocument();
    // default loader message should mention notes/indexing
    expect(screen.getByText(/Indexing your notes/i)).toBeInTheDocument();
  });

  it('renders main chrome when backend is ready', () => {
    vi.spyOn(backendHook, 'useBackendReady').mockReturnValue({ ready: true, error: null });
    vi.spyOn(statsHook, 'useStats').mockReturnValue({
      stats: {
        total_notes: 0,
        archived_notes: 0,
        pinned_notes: 0,
        using_cached_embeddings: false,
        image_search: { enabled: false },
      },
      isLoading: false,
      error: null,
      refetchStats: vi.fn(),
    });

    render(<App />);
    expect(screen.getByText('Google Keep Vibe Search')).toBeInTheDocument();
    // stats text should show counts even if zero
    expect(screen.getByText(/0 notes/)).toBeInTheDocument();
  });
});
