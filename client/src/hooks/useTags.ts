import { useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { TagCoverage, TagsResponse, ExcludedTagsResponse } from '@/types';

import { ApiError, QUERY_KEYS, fetchJson, invalidate } from './dataLayer';
import { useCachedQuery } from './useCachedQuery';

/**
 * Tags hook.
 *
 * Reads (`/api/tags`, `/api/tags/excluded`) are served from the shared cache
 * (see `dataLayer.ts`), so every component that mounts this hook shares one
 * request per endpoint instead of each firing its own. Mutations are uncached
 * POSTs; on success they invalidate the relevant cache keys, which refetches
 * the reads — replacing the old `await fetchTags()` callback chain.
 *
 * `onNotesChanged` is retained for callers that need to re-run an *uncached*
 * side-effect when note-tag membership changes — today only `Results` passes
 * it, to re-POST the active search. Cached reads (e.g. `useAllNotes`) refresh
 * automatically via `invalidate(QUERY_KEYS.NOTES)` and do not need it.
 */
export const useTags = (onNotesChanged?: () => void) => {
  const tagsQuery = useCachedQuery<TagsResponse>(API_ROUTES.TAGS);
  const excludedQuery = useCachedQuery<ExcludedTagsResponse>(API_ROUTES.EXCLUDED_TAGS);
  // Coverage lives under /api/tags, and invalidation matches by prefix, so every tag
  // mutation already refreshes it — no extra invalidate calls needed below.
  const coverageQuery = useCachedQuery<TagCoverage>(API_ROUTES.TAG_COVERAGE);
  const isLoading = tagsQuery.isLoading || excludedQuery.isLoading;
  const error = tagsQuery.error ?? excludedQuery.error;

  /** POST a mutation, mapping `ApiError` to the legacy string message. */
  const mutate = useCallback(
    async (
      url: string,
      body: unknown,
      method: 'POST' | 'DELETE' = 'POST',
    ): Promise<{ ok: true } | { ok: false; error: string }> => {
      try {
        await fetchJson(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        return { ok: true };
      } catch (err) {
        if (err instanceof ApiError) {
          return { ok: false, error: err.message };
        }
        return {
          ok: false,
          error: err instanceof Error ? err.message : 'An error occurred',
        };
      }
    },
    [],
  );

  /** Invalidate the caches touched by a note-tag membership change, then run
   *  the caller's uncached escape hatch (re-running a POST search). */
  const afterNotesChanged = useCallback(() => {
    invalidate(QUERY_KEYS.TAGS);
    invalidate(QUERY_KEYS.NOTES);
    invalidate(QUERY_KEYS.ALL_NOTES);
    onNotesChanged?.();
  }, [onNotesChanged]);

  const tagNotes = useCallback(
    async (noteIds: string[], tagName: string): Promise<void> => {
      const res = await mutate(API_ROUTES.TAG_NOTES, { note_ids: noteIds, tag_name: tagName });
      if (res.ok) {
        invalidate(QUERY_KEYS.TAGS);
        invalidate(QUERY_KEYS.NOTES);
        invalidate(QUERY_KEYS.ALL_NOTES);
      }
    },
    [mutate],
  );

  const updateExcludedTags = useCallback(
    async (newExcludedTags: string[]): Promise<void> => {
      const res = await mutate(API_ROUTES.EXCLUDED_TAGS, { excluded_tags: newExcludedTags });
      if (res.ok) {
        invalidate(QUERY_KEYS.EXCLUDED_TAGS);
      }
    },
    [mutate],
  );

  const removeTagFromNote = useCallback(
    async (noteId: string, tagName: string): Promise<void> => {
      const res = await mutate(
        `${API_ROUTES.REMOVE_TAG}/${noteId}/tag?tag_name=${encodeURIComponent(tagName)}`,
        {},
        'DELETE',
      );
      if (res.ok) {
        afterNotesChanged();
      }
    },
    [mutate, afterNotesChanged],
  );

  const removeTagFromAllNotes = useCallback(
    async (tagName: string): Promise<void> => {
      const res = await mutate(API_ROUTES.REMOVE_TAG_FROM_ALL, { tag_name: tagName });
      if (res.ok) {
        afterNotesChanged();
      }
    },
    [mutate, afterNotesChanged],
  );

  const renameTag = useCallback(
    async (oldName: string, newName: string): Promise<void> => {
      const res = await mutate(API_ROUTES.RENAME_TAG, { old_name: oldName, new_name: newName });
      if (res.ok) {
        afterNotesChanged();
      }
    },
    [mutate, afterNotesChanged],
  );

  const removeAllTags = useCallback(async (): Promise<void> => {
    const res = await mutate(API_ROUTES.REMOVE_ALL_TAGS, {}, 'DELETE');
    if (res.ok) {
      afterNotesChanged();
      invalidate(QUERY_KEYS.EXCLUDED_TAGS);
    }
  }, [mutate, afterNotesChanged]);

  return {
    tags: tagsQuery.data?.tags ?? [],
    excludedTags: excludedQuery.data?.excluded_tags ?? [],
    coverage: coverageQuery.data ?? null,
    isCoverageLoading: coverageQuery.isLoading,
    isLoading,
    error,
    tagNotes,
    updateExcludedTags,
    removeTagFromNote,
    removeTagFromAllNotes,
    removeAllTags,
    renameTag,
    refetchTags: tagsQuery.refetch,
    refetchExcludedTags: excludedQuery.refetch,
  };
};
