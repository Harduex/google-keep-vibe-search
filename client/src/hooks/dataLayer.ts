/**
 * Minimal in-house data layer for non-streaming GET endpoints.
 *
 * Background: the four read hooks (`useTags`,
 * `useStats`, `useAllNotes`, `useEmbeddings`) each held their own `useState` +
 * raw `fetch`, with no cache, dedupe or invalidation. `useTags` is mounted by
 * 7 components and auto-fetched two endpoints on mount, so each mount fired a
 * fresh request even when sibling mounts had just received identical data.
 *
 * This module provides three things, with no client dependency:
 *   1. `fetchJson`  — thin `fetch` wrapper that throws on non-2xx.
 *   2. `queryCache` — a URL-keyed cache with request dedupe (an in-flight
 *      promise is shared), a TTL, and prefix-based invalidation.
 *   3. a pub/sub     — React hooks subscribe so an invalidation or refetch in
 *      one component re-renders every other hook reading the same key.
 *
 * The two NDJSON streaming hooks (`useChat`, `useOrganize`) are deliberately
 * not routed through here — a streamed response is not a cacheable resource.
 */

/** Invalidation keys. Group a set of endpoints so a mutation can invalidate
 *  every cache entry that might reflect it, without callers hardcoding URLs. */
export const QUERY_KEYS = {
  STATS: '/api/stats',
  TAGS: '/api/tags',
  EXCLUDED_TAGS: '/api/tags/excluded',
  ALL_NOTES: '/api/all-notes',
  EMBEDDINGS: '/api/embeddings',
  // Note-tag membership changes invalidate both the tags list and the all-notes
  // list (note.tags change). Keep this prefix-stable; invalidation matches by
  // `String.startsWith`.
  NOTES: '/api/notes',
} as const;

/** Default TTL. Notes/tags/embeddings change only through this client, and we
 *  invalidate explicitly on every mutation, so a few minutes is plenty. */
const DEFAULT_TTL_MS = 5 * 60 * 1000;

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** Fetch and parse JSON, throwing `ApiError` on a non-2xx response. */
export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new ApiError(`HTTP error! status: ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

interface CacheEntry<T> {
  /** Resolved data, or `undefined` while the first request is in flight. */
  data?: T;
  /** Captured error so a failed request is shared across concurrent mounts. */
  error?: unknown;
  /** Wall-clock ms when this entry was populated (0 = never). */
  updatedAt: number;
  /** Shared in-flight promise — the dedupe handle. */
  promise?: Promise<T>;
}

const cache = new Map<string, CacheEntry<unknown>>();
const listeners = new Set<(key: string) => void>();

function notify(key: string): void {
  for (const fn of listeners) {
    fn(key);
  }
}

function isFresh(entry: CacheEntry<unknown>, ttl: number): boolean {
  return entry.updatedAt !== 0 && Date.now() - entry.updatedAt < ttl;
}

interface ReadResult<T> {
  data?: T;
  error?: unknown;
  /** `true` while the (possibly shared) request is in flight and no usable
   *  cached value exists yet. */
  isLoading: boolean;
  promise: Promise<T>;
}

/** Read a URL through the cache. Subsequent concurrent calls for the same key
 *  share a single network request (dedupe), and a fresh cache hit returns
 *  immediately without re-fetching. */
export function readQuery<T>(key: string, ttl = DEFAULT_TTL_MS): ReadResult<T> {
  let entry = cache.get(key) as CacheEntry<T> | undefined;
  if (!entry) {
    entry = { updatedAt: 0 };
    cache.set(key, entry as CacheEntry<unknown>);
  }

  // Fresh cache: no network.
  if (entry.data !== undefined && entry.error === undefined && isFresh(entry, ttl)) {
    return { data: entry.data, isLoading: false, promise: Promise.resolve(entry.data) };
  }

  // Dedupe: reuse an in-flight request for the same key.
  if (!entry.promise) {
    entry.promise = fetchJson<T>(key)
      .then((data) => {
        entry!.data = data;
        entry!.error = undefined;
        entry!.updatedAt = Date.now();
        notify(key);
        return data;
      })
      .catch((err: unknown) => {
        entry!.error = err;
        // Drop the in-flight handle so a later retry can re-issue the request.
        entry!.promise = undefined;
        notify(key);
        throw err;
      });
  }

  const isLoading = entry.data === undefined && entry.error === undefined;
  return {
    data: entry.data,
    error: entry.error,
    isLoading,
    promise: entry.promise,
  };
}

/** Subscribe to cache changes. Returns an unsubscribe function. */
export function subscribe(fn: (key: string) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Remove cache entries whose key starts with `keyPrefix`. Triggers a notify
 *  for each so any hook reading them refetches on its next render. */
export function invalidate(keyPrefix: string): void {
  const touched: string[] = [];
  for (const key of cache.keys()) {
    if (key === keyPrefix || key.startsWith(keyPrefix)) {
      cache.delete(key);
      touched.push(key);
    }
  }
  for (const key of touched) {
    notify(key);
  }
}

/** Clear the whole cache. Intended for tests; production invalidation should
 *  be scoped via `invalidate`. */
export function clearCache(): void {
  const keys = [...cache.keys()];
  cache.clear();
  for (const key of keys) {
    notify(key);
  }
}
