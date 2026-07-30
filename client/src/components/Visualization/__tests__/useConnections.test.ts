import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { invalidate } from '@/hooks/dataLayer';

import { connectionsUrl, useConnectionsFor } from '../useConnections';

const CONN = (id: string) => ({
  id,
  similar: [{ id: 'n2', title: 'Two', score: 0.9 }],
  shared_tags: [],
  shared_entities: [],
});

const okResponse = (body: unknown) =>
  ({ ok: true, status: 200, json: () => Promise.resolve(body) }) as Response;

afterEach(() => {
  // The data layer cache is module-global; drop our keys between tests.
  invalidate('/api/notes/');
  vi.unstubAllGlobals();
});

describe('useConnectionsFor', () => {
  it('fetches connections for every id and exposes them by id', async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(okResponse(CONN(url.split('/')[3]))));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useConnectionsFor(['n1']));
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.byId.n1).toBeDefined());
    expect(result.current.byId.n1.similar[0].id).toBe('n2');
    expect(result.current.isLoading).toBe(false);
    expect(fetchMock).toHaveBeenCalledWith(connectionsUrl('n1'), undefined);
  });

  it('surfaces per-id errors without throwing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 500, statusText: 'boom' } as Response)),
    );

    const { result } = renderHook(() => useConnectionsFor(['bad']));
    await waitFor(() => expect(result.current.errors.bad).toBeDefined());
    expect(result.current.byId.bad).toBeUndefined();
  });

  it('grows the map as the chain grows, without refetching cached ids', async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(okResponse(CONN(url.split('/')[3]))));
    vi.stubGlobal('fetch', fetchMock);

    const { result, rerender } = renderHook(({ ids }) => useConnectionsFor(ids), {
      initialProps: { ids: ['n1'] },
    });
    await waitFor(() => expect(result.current.byId.n1).toBeDefined());

    act(() => rerender({ ids: ['n1', 'n2'] }));
    await waitFor(() => expect(result.current.byId.n2).toBeDefined());
    // n1 came from the cache the second time round.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
