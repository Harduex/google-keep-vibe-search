import { useState, useCallback, useEffect } from 'react';

import { API_ROUTES } from '@/const';
import { NoteCluster } from '@/types';
import { useError } from '@/hooks/useError';

interface UseClustersResult {
  clusters: NoteCluster[];
  isLoading: boolean;
  error: string | null;
  fetchClusters: (numClusters?: number) => Promise<void>;
}

export const useClusters = (initialNumClusters?: number): UseClustersResult => {
  const [clusters, setClusters] = useState<NoteCluster[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { error, handleError, clearError } = useError();

  const fetchClusters = useCallback(
    async (numClusters?: number): Promise<void> => {
      try {
        setIsLoading(true);
        clearError();

        const url = new URL(`${window.location.origin}${API_ROUTES.CLUSTERS}`);
        if (numClusters) {
          url.searchParams.append('num_clusters', numClusters.toString());
        }

        const response = await fetch(url);

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        setClusters(data.clusters || []);
      } catch (err) {
        handleError(err);
        setClusters([]);
      } finally {
        setIsLoading(false);
      }
    },
    [clearError, handleError]
  );

  // Fetch clusters on initial load if initialNumClusters is provided
  useEffect(() => {
    if (initialNumClusters) {
      fetchClusters(initialNumClusters);
    }
  }, [initialNumClusters, fetchClusters]);

  return { clusters, isLoading, error, fetchClusters };
};
