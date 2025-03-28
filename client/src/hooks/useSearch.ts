import { useState, useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { useError } from '@/hooks/useError';
import { Note } from '@/types/index';

interface UseSearchResult {
  query: string;
  results: Note[];
  isLoading: boolean;
  hasSearched: boolean;
  error: string | null;
  semanticWeight: number;
  setSemanticWeight: (weight: number) => void;
  threshold: number;
  setThreshold: (threshold: number) => void;
  performSearch: (searchQuery: string) => Promise<void>;
}

export const useSearch = (): UseSearchResult => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Note[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [semanticWeight, setSemanticWeight] = useState<number>(0.7); // Default to 0.7 (70% semantic, 30% keyword)
  const [threshold, setThreshold] = useState<number>(0.1); // Default to 0.1 (10% threshold)
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

        const response = await fetch(`${API_ROUTES.SEARCH}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query: searchQuery,
            semanticWeight: semanticWeight,
            threshold: threshold,
          }),
        });

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
    [clearError, handleError, semanticWeight, threshold],
  );

  return {
    query,
    results,
    isLoading,
    hasSearched,
    error,
    semanticWeight,
    setSemanticWeight,
    threshold,
    setThreshold,
    performSearch,
  };
};
