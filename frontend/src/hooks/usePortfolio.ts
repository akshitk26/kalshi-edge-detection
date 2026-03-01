import { useState, useEffect, useCallback, useRef } from "react";
import type {
  PortfolioData,
  PortfolioHistory,
  PortfolioSnapshot,
  PortfolioStats,
} from "../types/portfolio";

const API_BASE = "http://localhost:5050";

interface UsePortfolioResult {
  configured: boolean | null;
  data: PortfolioData | null;
  history: PortfolioSnapshot[];
  stats: PortfolioStats | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function usePortfolio(): UsePortfolioResult {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [data, setData] = useState<PortfolioData | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval>>(null);

  const fetchAll = useCallback(async () => {
    try {
      const statusRes = await fetch(`${API_BASE}/api/portfolio/status`);
      const statusData = await statusRes.json();
      setConfigured(statusData.configured);

      if (!statusData.configured) {
        setLoading(false);
        return;
      }

      const [balanceRes, historyRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/portfolio/balance`),
        fetch(`${API_BASE}/api/portfolio/history`),
        fetch(`${API_BASE}/api/portfolio/stats`),
      ]);

      if (!balanceRes.ok) throw new Error("Failed to fetch balance");
      if (!historyRes.ok) throw new Error("Failed to fetch history");

      const balanceData: PortfolioData = await balanceRes.json();
      const historyData: PortfolioHistory = await historyRes.json();

      setData(balanceData);
      setHistory(historyData.snapshots);

      if (statsRes.ok) {
        setStats(await statsRes.json());
      }

      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, 30_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchAll]);

  return { configured, data, history, stats, loading, error, refresh: fetchAll };
}
