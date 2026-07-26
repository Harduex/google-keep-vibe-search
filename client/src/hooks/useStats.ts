import { API_ROUTES } from '@/const';

import { useCachedQuery } from './useCachedQuery';

interface StatsResponse {
  total_notes: number;
  archived_notes: number;
  pinned_notes: number;
  using_cached_embeddings: boolean;
  image_search: {
    enabled: boolean;
  };
}

interface UseStatsResult {
  stats: StatsResponse | null;
  isLoading: boolean;
  error: string | null;
  refetchStats: () => Promise<void>;
}

export const useStats = (enabled = true): UseStatsResult => {
  // `key` is `null` when disabled so the cache is never read or written — that
  // matches the previous behaviour of not fetching until the backend is ready.
  const key = enabled ? API_ROUTES.STATS : null;
  const { data, isLoading, error, refetch } = useCachedQuery<StatsResponse>(key);
  return { stats: data ?? null, isLoading, error, refetchStats: refetch };
};
