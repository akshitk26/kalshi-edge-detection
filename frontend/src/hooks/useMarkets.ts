import { useState, useEffect, useCallback, useRef } from "react";
import type { MarketRow, MarketsResponse } from "../types/market";

const API_BASE = "/api";
const DEFAULT_INTERVAL = 30_000; // 30 seconds

interface UseMarketsResult {
  markets: MarketRow[];
  meta: MarketsResponse["meta"] | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
  lastRefresh: Date | null;
  paused: boolean;
  togglePause: () => void;
}

export function useMarkets(): UseMarketsResult {
  const [markets, setMarkets] = useState<MarketRow[]>([]);
  const [meta, setMeta] = useState<MarketsResponse["meta"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [paused, setPaused] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMarkets = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/markets`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      const data: MarketsResponse = await res.json();
      setMarkets(data.markets);
      setMeta(data.meta);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchMarkets();
  }, [fetchMarkets]);

  // Auto-refresh interval (runs unless paused)
  useEffect(() => {
    if (paused) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    intervalRef.current = setInterval(fetchMarkets, DEFAULT_INTERVAL);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [paused, fetchMarkets]);

  const togglePause = useCallback(() => {
    setPaused((prev) => {
      if (prev) {
        // Resuming — refresh immediately
        fetchMarkets();
      }
      return !prev;
    });
  }, [fetchMarkets]);

  return {
    markets,
    meta,
    loading,
    error,
    refresh: fetchMarkets,
    lastRefresh,
    paused,
    togglePause,
  };
}
