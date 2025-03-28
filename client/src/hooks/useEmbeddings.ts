import { useState, useEffect, useCallback } from 'react';

import { API_ROUTES } from '@/const';

import { useError } from './useError';

export interface EmbeddingPoint {
  id: string;
  title: string;
  content: string;
  coordinates: [number, number, number];
}

interface UseEmbeddingsResult {
  embeddings: EmbeddingPoint[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export const useEmbeddings = (): UseEmbeddingsResult => {
  const [embeddings, setEmbeddings] = useState<EmbeddingPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { error, handleError, clearError } = useError();

  const fetchEmbeddings = useCallback(async () => {
    try {
      setIsLoading(true);
      clearError();

      const response = await fetch(API_ROUTES.EMBEDDINGS);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setEmbeddings(data.embeddings || []);
    } catch (err) {
      handleError(err);
    } finally {
      setIsLoading(false);
    }
  }, [handleError, clearError]);

  useEffect(() => {
    fetchEmbeddings();
  }, [fetchEmbeddings]);

  return { embeddings, isLoading, error, refetch: fetchEmbeddings };
};
