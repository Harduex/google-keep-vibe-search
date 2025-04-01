import { useState, useCallback, useMemo } from 'react';

import { API_ROUTES } from '@/const';
import { filterByKeywords } from '@/helpers';
import { useError } from '@/hooks/useError';
import { Note } from '@/types/index';

interface UseSearchResult {
  query: string;
  results: Note[];
  originalResults: Note[];
  refinementKeywords: string;
  isLoading: boolean;
  hasSearched: boolean;
  isRefined: boolean;
  error: string | null;
  performSearch: (searchQuery: string) => Promise<void>;
  refineResults: (keywords: string) => void;
  resetRefinement: () => void;
  setResults: (results: Note[]) => void; // New method to set results directly
  setLoading: (loading: boolean) => void; // New method to manage loading state
}

export const useSearch = (): UseSearchResult => {
  const [query, setQuery] = useState('');
  const [originalResults, setOriginalResults] = useState<Note[]>([]);
  const [refinementKeywords, setRefinementKeywords] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const { error, handleError, clearError } = useError();

  // Apply refinement filter to original results
  const results = useMemo(() => {
    return filterByKeywords(originalResults, refinementKeywords);
  }, [originalResults, refinementKeywords]);

  const performSearch = useCallback(
    async (searchQuery: string): Promise<void> => {
      if (!searchQuery.trim()) {
        return;
      }

      try {
        setIsLoading(true);
        clearError();
        setQuery(searchQuery);
        setRefinementKeywords(''); // Clear refinement when performing a new search

        const response = await fetch(`${API_ROUTES.SEARCH}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ query: searchQuery }),
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        setOriginalResults(data.results || []);
        setHasSearched(true);
      } catch (err) {
        handleError(err);
        setOriginalResults([]);
      } finally {
        setIsLoading(false);
      }
    },
    [clearError, handleError],
  );

  const refineResults = useCallback((keywords: string) => {
    setRefinementKeywords(keywords);
  }, []);

  const resetRefinement = useCallback(() => {
    setRefinementKeywords('');
  }, []);

  // New method to set results directly (useful for image search)
  const setResults = useCallback((results: Note[]) => {
    setOriginalResults(results);
    setHasSearched(true);
  }, []);

  // New method to control loading state externally
  const setLoading = useCallback((loading: boolean) => {
    setIsLoading(loading);
  }, []);

  return {
    query,
    results,
    originalResults,
    refinementKeywords,
    isLoading,
    hasSearched,
    isRefined: !!refinementKeywords,
    error,
    performSearch,
    refineResults,
    resetRefinement,
    setResults,
    setLoading,
  };
};
