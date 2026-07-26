import { API_ROUTES } from '@/const';
import { Note } from '@/types';

import { useCachedQuery } from './useCachedQuery';

interface UseAllNotesResult {
  notes: Note[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

interface AllNotesResponse {
  notes?: Note[];
}

export const useAllNotes = (): UseAllNotesResult => {
  const { data, isLoading, error, refetch } = useCachedQuery<AllNotesResponse>(
    API_ROUTES.ALL_NOTES,
  );
  return { notes: data?.notes ?? [], isLoading, error, refetch };
};
