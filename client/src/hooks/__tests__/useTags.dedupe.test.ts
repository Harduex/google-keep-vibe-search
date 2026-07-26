import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { clearCache } from '../dataLayer';
import { useTags } from '../useTags';

const originalFetch = global.fetch;

/**
 * A11/T30: `useTags` is mounted by 7 components, and before the data layer it
 * fired its own `/api/tags` + `/api/tags/excluded` request on every mount.
 * Three mounts of `useTags` must now share a single request per endpoint.
 */
describe('useTags dedupe across mounts', () => {
  beforeEach(() => {
    clearCache();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    global.fetch = vi.fn(async (input: string) => {
      if (input === '/api/tags') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tags: [] }),
        } as Response);
      }
      if (input === '/api/tags/excluded') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ excluded_tags: [] }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('issues exactly one /api/tags request when three components mount', async () => {
    renderHook(() => useTags());
    renderHook(() => useTags());
    renderHook(() => useTags());

    // Let the shared in-flight request resolve and any re-renders settle.
    await waitFor(() => {
      const tagsCalls = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.filter(
        (c) => c[0] === '/api/tags',
      );
      expect(tagsCalls).toHaveLength(1);
    });

    const allCalls = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(
      (c) => c[0],
    );
    expect(allCalls.filter((u) => u === '/api/tags')).toHaveLength(1);
    expect(allCalls.filter((u) => u === '/api/tags/excluded')).toHaveLength(1);
  });

  it('refetches /api/tags exactly once after a mutation invalidates the key', async () => {
    const { result } = renderHook(() => useTags());
    await waitFor(() => {
      expect(result.current.tags).toEqual([]);
    });

    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockClear();

    await result.current.removeTagFromAllNotes('Old');

    await waitFor(() => {
      const tagsCalls = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.filter(
        (c) => c[0] === '/api/tags',
      );
      expect(tagsCalls).toHaveLength(1);
    });
  });
});
