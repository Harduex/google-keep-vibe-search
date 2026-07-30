import { API_ROUTES } from '@/const';

import { useCachedQuery } from './useCachedQuery';

export interface EmbeddingPoint {
  id: string;
  title: string;
  /** First ~120 chars of the note, for hover labels only. */
  snippet: string;
  /** Tags the note carries, resolved server-side from the tag map (used to colour points). */
  tags: string[];
  coordinates: [number, number, number];
}

interface UseEmbeddingsResult {
  embeddings: EmbeddingPoint[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

interface EmbeddingsResponse {
  embeddings?: EmbeddingPoint[];
}

export const useEmbeddings = (): UseEmbeddingsResult => {
  const { data, isLoading, error, refetch } = useCachedQuery<EmbeddingsResponse>(
    API_ROUTES.EMBEDDINGS,
  );
  return { embeddings: data?.embeddings ?? [], isLoading, error, refetch };
};
