import { useCallback, useEffect, useState } from 'react';

import { API_ROUTES } from '../constants/ui';
import { StatsResponse } from '../types';
import { useError } from './useError';

interface UseStatsResult {
  stats: StatsResponse | null;
  isLoading: boolean;
  error: string | null;
  refetchStats: () => Promise<void>;
}

export const useStats = (): UseStatsResult => {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { error, handleError, clearError } = useError();

  const fetchStats = useCallback(async (): Promise<void> => {
    try {
      setIsLoading(true);
      clearError();
      const response = await fetch(API_ROUTES.STATS);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setStats(data);
    } catch (err) {
      handleError(err);
    } finally {
      setIsLoading(false);
    }
  }, [clearError, handleError]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return { stats, isLoading, error, refetchStats: fetchStats };
};
