import { useCallback, useEffect, useRef, useState } from 'react';

import { API_ROUTES } from '@/const';

interface HealthResponse {
  status: string;
  ready: boolean;
  total_notes: number;
  services: {
    notes: boolean;
    search: boolean;
    chat: boolean;
    lancedb: boolean;
    graphrag: boolean;
    raptor: boolean;
  };
}

interface UseBackendHealthResult {
  isConnected: boolean;
  isReady: boolean;
  totalNotes: number;
  health: HealthResponse | null;
}

const POLL_INTERVAL_MS = 3000;

export const useBackendHealth = (): UseBackendHealthResult => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(API_ROUTES.HEALTH);
      if (response.ok) {
        const data: HealthResponse = await response.json();
        setHealth(data);
        setIsConnected(true);
        return data.ready;
      }
      setIsConnected(false);
      return false;
    } catch {
      setIsConnected(false);
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      const ready = await checkHealth();
      if (ready && !cancelled) {
        // Backend is fully ready — stop polling
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };

    // Initial check
    poll();

    // Start polling until ready
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [checkHealth]);

  return {
    isConnected,
    isReady: health?.ready ?? false,
    totalNotes: health?.total_notes ?? 0,
    health,
  };
};
