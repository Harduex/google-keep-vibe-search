import { useEffect, useState } from 'react';

import { API_ROUTES } from '@/const';

interface UseBackendReadyResult {
  ready: boolean;
  error: string | null;
}

/**
 * Polls the backend until it reports that startup/indexing has finished.
 *
 * The server exposes a simple `/api/ready` endpoint that returns `{"ready":
 * true}` once the lifespan handler has finished loading notes, computing
 * embeddings and performing any other expensive work.  While the value is
 * false we keep retrying every second and expose the flag to callers so they
 * can show a fullscreen loading screen.
 */
export const useBackendReady = (): UseBackendReadyResult => {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const resp = await fetch(API_ROUTES.READY);
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }

        const data = (await resp.json()) as { ready?: boolean };
        if (!cancelled) {
          if (data.ready) {
            setReady(true);
          } else {
            // keep polling until backend reports ready
            setTimeout(check, 1000);
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || 'unable to contact server');
          // retry in a second; we don't escalate into a permanent error so the
          // user stays on the loading screen rather than seeing an error banner
          setTimeout(check, 1000);
        }
      }
    };

    check();

    return () => {
      cancelled = true;
    };
  }, []);

  return { ready, error };
};
