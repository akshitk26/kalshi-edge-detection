import { useState, useEffect, useCallback } from "react";
import type { MarketRow, MarketsResponse } from "../types/market";

const API_BASE = "/api";

interface UseMarketsResult {
  markets: MarketRow[];
  meta: MarketsResponse["meta"] | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
  lastRefresh: Date | null;
}

export function useMarkets(autoRefreshMs = 0): UseMarketsResult {
  const [markets, setMarkets] = useState<MarketRow[]>([]);
  const [meta, setMeta] = useState<MarketsResponse["meta"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

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

  useEffect(() => {
    fetchMarkets();
  }, [fetchMarkets]);

  useEffect(() => {
    if (autoRefreshMs <= 0) return;
    const id = setInterval(fetchMarkets, autoRefreshMs);
    return () => clearInterval(id);
  }, [autoRefreshMs, fetchMarkets]);

  return { markets, meta, loading, error, refresh: fetchMarkets, lastRefresh };
}
