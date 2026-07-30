import { useEffect, useMemo, useRef, useState } from 'react';

import { API_ROUTES } from '@/const';
import { readQuery, subscribe } from '@/hooks/dataLayer';

export interface ConnectionNoteRef {
  id: string;
  title: string;
}
export interface SimilarConnection extends ConnectionNoteRef {
  score: number;
}
export interface TagConnectionGroup {
  tag: string;
  notes: ConnectionNoteRef[];
}
export interface EntityConnectionGroup {
  entity: string;
  notes: ConnectionNoteRef[];
}
export interface NoteConnections {
  id: string;
  similar: SimilarConnection[];
  shared_tags: TagConnectionGroup[];
  shared_entities: EntityConnectionGroup[];
}

export const connectionsUrl = (noteId: string): string =>
  `${API_ROUTES.NOTE_CONNECTIONS}/${encodeURIComponent(noteId)}/connections`;

/**
 * Connections for every note in the selection chain, read through the shared
 * data-layer cache. Each id is fetched once (the cache dedupes); expanding the
 * chain only fetches the new id.
 */
export function useConnectionsFor(ids: string[]): {
  byId: Record<string, NoteConnections>;
  errors: Record<string, string>;
  isLoading: boolean;
} {
  // `tick` only forces a re-read of the cache; the data itself lives there. It is
  // in the memo deps too — the cache entry mutates in place, so a changed `key`
  // alone would never re-run the read.
  const [tick, setTick] = useState(0);
  const key = ids.join('|');
  // Ids whose fetch failed, latched. `readQuery` drops its in-flight handle on
  // failure so a later call re-issues the request — and since a failure also
  // notifies, re-reading a failed key here would spin: read -> fetch -> fail ->
  // notify -> read. Latching stops the loop at one retry; a failed connection
  // set stays failed until the view remounts.
  const failedRef = useRef<Record<string, string>>({});

  useEffect(() => {
    const urls = new Set(ids.map(connectionsUrl));
    return subscribe((changed) => {
      if (urls.has(changed)) {
        setTick((t) => t + 1);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return useMemo(() => {
    const byId: Record<string, NoteConnections> = {};
    const errors: Record<string, string> = {};
    let isLoading = false;
    ids.forEach((id) => {
      const failed = failedRef.current[id];
      if (failed !== undefined) {
        errors[id] = failed;
        return;
      }
      const res = readQuery<NoteConnections>(connectionsUrl(id));
      // The shared promise must not surface as an unhandled rejection here; the
      // error lands in the cache and comes back via `res.error`.
      res.promise.catch(() => undefined);
      if (res.data) {
        byId[id] = res.data;
      }
      if (res.error !== undefined) {
        const message = res.error instanceof Error ? res.error.message : String(res.error);
        failedRef.current[id] = message;
        errors[id] = message;
      }
      if (res.isLoading) {
        isLoading = true;
      }
    });
    return { byId, errors, isLoading };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick]);
}
