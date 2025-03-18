import { useState, useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { Note } from '@/types/index';
import { useError } from '@/hooks/useError';

interface UseSearchResult {
  query: string;
  results: Note[];
  isLoading: boolean;
  hasSearched: boolean;
  error: string | null;
  performSearch: (searchQuery: string) => Promise<void>;
}

export const useSearch = (): UseSearchResult => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Note[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const { error, handleError, clearError } = useError();

  const performSearch = useCallback(
    async (searchQuery: string): Promise<void> => {
      if (!searchQuery.trim()) {
        return;
      }

      try {
        setIsLoading(true);
        clearError();
        setQuery(searchQuery);

        const response = await fetch(`${API_ROUTES.SEARCH}?q=${encodeURIComponent(searchQuery)}`);

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        setResults(data.results || []);
        setHasSearched(true);
      } catch (err) {
        handleError(err);
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    },
    [clearError, handleError]
  );

  return {
    query,
    results,
    isLoading,
    hasSearched,
    error,
    performSearch,
  };
};
