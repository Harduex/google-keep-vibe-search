import { useState, useCallback } from 'react';

interface UseErrorResult {
  error: string | null;
  setError: (error: string | null) => void;
  handleError: (err: unknown) => void;
  clearError: () => void;
}

export const useError = (): UseErrorResult => {
  const [error, setError] = useState<string | null>(null);

  const handleError = useCallback((err: unknown) => {
    if (err instanceof Error) {
      setError(err.message);
    } else if (typeof err === 'string') {
      setError(err);
    } else {
      setError('An unknown error occurred');
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    error,
    setError,
    handleError,
    clearError,
  };
};
