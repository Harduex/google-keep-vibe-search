import { useState, useEffect, useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { Note } from '@/types';
import { useError } from '@/hooks/useError';

interface UseAllNotesResult {
  notes: Note[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export const useAllNotes = (): UseAllNotesResult => {
  const [notes, setNotes] = useState<Note[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { error, handleError, clearError } = useError();

  const fetchNotes = useCallback(async (): Promise<void> => {
    try {
      setIsLoading(true);
      clearError();
      const response = await fetch(`${API_ROUTES.ALL_NOTES}`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setNotes(data.notes || []);
    } catch (err) {
      handleError(err);
      setNotes([]);
    } finally {
      setIsLoading(false);
    }
  }, [clearError, handleError]);

  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  return { notes, isLoading, error, refetch: fetchNotes };
};
