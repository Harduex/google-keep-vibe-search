import { useState, useEffect, useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { Tag, TagsResponse, ExcludedTagsResponse } from '@/types';

export const useTags = () => {
  const [tags, setTags] = useState<Tag[]>([]);
  const [excludedTags, setExcludedTags] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTags = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await fetch(API_ROUTES.TAGS);
      if (!response.ok) {
        throw new Error('Failed to fetch tags');
      }
      const data: TagsResponse = await response.json();
      setTags(data.tags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchExcludedTags = useCallback(async () => {
    try {
      const response = await fetch(API_ROUTES.EXCLUDED_TAGS);
      if (!response.ok) {
        throw new Error('Failed to fetch excluded tags');
      }
      const data: ExcludedTagsResponse = await response.json();
      setExcludedTags(data.excluded_tags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  }, []);

  const tagNotes = useCallback(
    async (noteIds: string[], tagName: string) => {
      try {
        setIsLoading(true);
        const response = await fetch(API_ROUTES.TAG_NOTES, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            note_ids: noteIds,
            tag_name: tagName,
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to tag notes');
        }

        // Refresh tags after successful tagging
        await fetchTags();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setIsLoading(false);
      }
    },
    [fetchTags],
  );

  const updateExcludedTags = useCallback(async (newExcludedTags: string[]) => {
    try {
      setIsLoading(true);
      const response = await fetch(API_ROUTES.EXCLUDED_TAGS, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          excluded_tags: newExcludedTags,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to update excluded tags');
      }

      setExcludedTags(newExcludedTags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const removeTagFromNote = useCallback(
    async (noteId: string) => {
      try {
        setIsLoading(true);
        const response = await fetch(`${API_ROUTES.REMOVE_TAG}/${noteId}/tag`, {
          method: 'DELETE',
        });

        if (!response.ok) {
          throw new Error('Failed to remove tag');
        }

        // Refresh tags after successful removal
        await fetchTags();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setIsLoading(false);
      }
    },
    [fetchTags],
  );

  useEffect(() => {
    fetchTags();
    fetchExcludedTags();
  }, [fetchTags, fetchExcludedTags]);

  return {
    tags,
    excludedTags,
    isLoading,
    error,
    tagNotes,
    updateExcludedTags,
    removeTagFromNote,
    refetchTags: fetchTags,
    refetchExcludedTags: fetchExcludedTags,
  };
};
