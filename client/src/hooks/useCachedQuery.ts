import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, readQuery, subscribe } from './dataLayer';

export interface CachedQueryResult<T> {
  data: T | undefined;
  isLoading: boolean;
  error: string | null;
  /** Force a fresh network request, bypassing the TTL. */
  refetch: () => Promise<void>;
}

interface UseCachedQueryOptions {
  /** Skip the initial fetch entirely (e.g. while the backend is still warming
   *  up — see `useStats(backendReady)`). */
  enabled?: boolean;
  /** Cache TTL in ms. Defaults to the data layer's value. */
  ttl?: number;
}

/**
 * React binding over `readQuery`. The cache is the single source of truth: the
 * first mount for a key fires the request, concurrent mounts share it, and an
 * `invalidate` anywhere in the tree causes this hook to refetch.
 *
 * The hook deliberately does *not* return a `force-network` flag on every read
 * — explicit refreshes go through `refetch` or invalidation, so re-renders of
 * the host component stay free.
 */
export function useCachedQuery<T>(
  key: string | null,
  options: UseCachedQueryOptions = {},
): CachedQueryResult<T> {
  const { enabled = true, ttl } = options;
  // `tick` only forces React to re-read the cache; data itself lives there.
  const [tick, setTick] = useState(0);
  const mountedRef = useRef(true);
  // The in-flight promise we have already attached an error observer to, so the
  // same shared request does not produce an unhandled rejection per render.
  const observedPromiseRef = useRef<Promise<unknown> | undefined>(undefined);

  useEffect(() => {
    mountedRef.current = true;
    const unsubscribe = subscribe((changed) => {
      if (!mountedRef.current) {
        return;
      }
      if (key === null || changed === key) {
        setTick((t) => t + 1);
      }
    });
    return () => {
      mountedRef.current = false;
      unsubscribe();
    };
  }, [key]);

  const refetch = useCallback(async (): Promise<void> => {
    if (key === null) {
      return;
    }
    try {
      await readQuery<T>(key, ttl).promise;
    } catch {
      // surfaced via cache state below; swallow here to avoid unhandled rejection
    }
    if (mountedRef.current) {
      setTick((t) => t + 1);
    }
  }, [key, ttl]);

  if (key === null || !enabled) {
    return { data: undefined, isLoading: false, error: null, refetch };
  }

  // Read on every render; the subscription above bumps `tick` whenever the
  // cache changes so this render reflects the latest value.
  void tick;
  const snapshot = readQuery<T>(key, ttl);

  // Observe the in-flight promise exactly once so a rejection is caught by the
  // cache (which stores it in `entry.error`) rather than escaping unhandled.
  // The data/error we render come from `snapshot`, not from this await.
  if (snapshot.isLoading && snapshot.promise && observedPromiseRef.current !== snapshot.promise) {
    observedPromiseRef.current = snapshot.promise;
    snapshot.promise.catch(() => {
      /* handled: the cache captured the error and notified subscribers */
    });
  }

  const message =
    snapshot.error instanceof ApiError
      ? snapshot.error.message
      : snapshot.error instanceof Error
        ? snapshot.error.message
        : snapshot.error
          ? 'An error occurred'
          : null;

  return {
    data: snapshot.data,
    isLoading: snapshot.isLoading,
    error: message,
    refetch,
  };
}
