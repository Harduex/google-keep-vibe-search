import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { clearCache, fetchJson, invalidate, readQuery, subscribe, ApiError } from '../dataLayer';

const originalFetch = global.fetch;

const makeFetcher = () => {
  const calls: string[] = [];
  const fn = vi.fn((url: string | URL | Request) => {
    calls.push(String(url));
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ url: String(url) }),
    } as Response);
  });
  return { fn, calls };
};

describe('dataLayer', () => {
  beforeEach(() => {
    clearCache();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe('fetchJson', () => {
    it('returns parsed JSON on a 2xx response', async () => {
      global.fetch = vi.fn(async () =>
        Promise.resolve({ ok: true, json: async () => ({ a: 1 }) } as Response),
      );
      const data = await fetchJson<{ a: number }>('/x');
      expect(data).toEqual({ a: 1 });
    });

    it('throws ApiError with the status on a non-2xx response', async () => {
      global.fetch = vi.fn(async () => Promise.resolve({ ok: false, status: 500 } as Response));
      await expect(fetchJson('/x')).rejects.toMatchObject({
        name: 'ApiError',
        status: 500,
      });
      expect(ApiError).toBeDefined();
    });
  });

  describe('readQuery dedupe + cache', () => {
    it('fires one network request for concurrent reads of the same key', async () => {
      const { fn, calls } = makeFetcher();
      global.fetch = fn;

      const a = readQuery('/same');
      const b = readQuery('/same');
      const c = readQuery('/same');
      await Promise.all([a.promise, b.promise, c.promise]);

      expect(calls).toEqual(['/same']);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('serves subsequent reads from cache without re-fetching', async () => {
      const { fn } = makeFetcher();
      global.fetch = fn;

      await readQuery('/k').promise;
      const first = readQuery('/k');
      const second = readQuery('/k');
      expect(first.data).toEqual({ url: '/k' });
      expect(second.data).toEqual({ url: '/k' });
      expect(first.isLoading).toBe(false);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('shares a failed request across concurrent readers and allows a retry', async () => {
      const failing = vi.fn(async () => Promise.resolve({ ok: false, status: 503 } as Response));
      global.fetch = failing;

      const a = readQuery('/fail');
      const b = readQuery('/fail');
      // The shared in-flight promise rejects for both readers.
      await expect(a.promise).rejects.toBeInstanceOf(ApiError);
      await expect(b.promise).rejects.toBeInstanceOf(ApiError);
      expect(failing).toHaveBeenCalledTimes(1);

      // After failure a new read re-issues the request (no sticky error) and
      // can succeed once the backend recovers.
      const ok = vi.fn(async () =>
        Promise.resolve({ ok: true, json: async () => ({ recovered: true }) } as Response),
      );
      global.fetch = ok;
      await readQuery('/fail').promise;
      const third = readQuery('/fail');
      expect(third.error).toBeUndefined();
      expect(third.data).toEqual({ recovered: true });
    });
  });

  describe('invalidate', () => {
    it('clears matching keys and leaves the rest', async () => {
      const { fn } = makeFetcher();
      global.fetch = fn;

      await readQuery('/api/tags').promise;
      await readQuery('/api/tags/excluded').promise;
      await readQuery('/api/stats').promise;
      expect(fn).toHaveBeenCalledTimes(3);

      invalidate('/api/tags');
      // both /api/tags and /api/tags/excluded match the prefix; /api/stats does not
      expect(readQuery('/api/tags').isLoading).toBe(true);
      expect(readQuery('/api/tags/excluded').isLoading).toBe(true);
      expect(readQuery('/api/stats').data).toEqual({ url: '/api/stats' });
    });

    it('notifies subscribers for each cleared key', async () => {
      const { fn } = makeFetcher();
      global.fetch = fn;
      await readQuery('/api/tags').promise;
      await readQuery('/api/stats').promise;

      const seen: string[] = [];
      const unsub = subscribe((k) => seen.push(k));
      invalidate('/api/tags');
      expect(seen).toContain('/api/tags');
      expect(seen).not.toContain('/api/stats');
      unsub();
    });
  });

  describe('subscribe', () => {
    it('notifies on a successful populate', async () => {
      const { fn } = makeFetcher();
      global.fetch = fn;
      const seen: string[] = [];
      const unsub = subscribe((k) => seen.push(k));
      await readQuery('/fresh').promise;
      expect(seen).toContain('/fresh');
      unsub();
    });
  });
});
