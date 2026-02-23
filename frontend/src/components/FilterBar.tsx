import { useState, useMemo, useEffect } from "react";
import type { MarketRow, SortConfig, SortField, SortDirection } from "../types/market";

/** All cities the backend probability model supports. */
const ALL_CITIES = [
  "Atlanta",
  "Boston",
  "Chicago",
  "Dallas",
  "Denver",
  "Houston",
  "Las Vegas",
  "Los Angeles",
  "Miami",
  "Minneapolis",
  "New Orleans",
  "New York",
  "Philadelphia",
  "Phoenix",
  "San Francisco",
  "Seattle",
] as const;

interface FilterBarProps {
  markets: MarketRow[];
  onCityChange: (city: string) => void;
  onDateChange: (date: string) => void;
  selectedCity: string;
  selectedDate: string;
  lastRefresh: Date | null;
  onRefresh: () => void;
  loading: boolean;
  priceSource: string;
  paused: boolean;
  onTogglePause: () => void;
}

function formatEST(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }) + " EST";
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s ago`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s ago`;
}

function ElapsedTimer({ since }: { since: Date }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setElapsed(Math.floor((Date.now() - since.getTime()) / 1000));
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - since.getTime()) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [since]);

  return <span className="elapsed-timer">{formatElapsed(elapsed)}</span>;
}

export function FilterBar({
  markets,
  onCityChange,
  onDateChange,
  selectedCity,
  selectedDate,
  lastRefresh,
  onRefresh,
  loading,
  priceSource,
  paused,
  onTogglePause,
}: FilterBarProps) {
  const dates = useMemo(() => {
    const set = new Set(markets.map((m) => m.date).filter(Boolean));
    return Array.from(set).sort();
  }, [markets]);

  return (
    <div className="filter-bar">
      <div className="filter-group">
        <label htmlFor="city-filter">City</label>
        <select
          id="city-filter"
          value={selectedCity}
          onChange={(e) => onCityChange(e.target.value)}
        >
          <option value="">All</option>
          {ALL_CITIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="date-filter">Date</label>
        <select
          id="date-filter"
          value={selectedDate}
          onChange={(e) => onDateChange(e.target.value)}
        >
          <option value="">All</option>
          {dates.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-meta">
        <span className="meta-label">Source: {priceSource || "—"}</span>
        {lastRefresh && (
          <span className="meta-label refresh-info">
            Last refresh: {formatEST(lastRefresh)}
            {paused && (
              <>
                {" · "}
                <ElapsedTimer since={lastRefresh} />
              </>
            )}
          </span>
        )}
        <button
          className={`pause-btn ${paused ? "paused" : ""}`}
          onClick={onTogglePause}
          title={paused ? "Resume auto-refresh" : "Freeze auto-refresh"}
        >
          {paused ? "▶ Resume" : "❄ Freeze"}
        </button>
        <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
          {loading ? "…" : "Refresh"}
        </button>
      </div>
    </div>
  );
}

/* ─── Sort hook ─── */
export function useSortedMarkets(
  markets: MarketRow[],
  initialField: SortField = "edge",
  initialDir: SortDirection = "desc"
) {
  const [sort, setSort] = useState<SortConfig>({
    field: initialField,
    direction: initialDir,
  });

  const toggleSort = (field: SortField) => {
    setSort((prev) => ({
      field,
      direction:
        prev.field === field && prev.direction === "desc" ? "asc" : "desc",
    }));
  };

  const sorted = useMemo(() => {
    const copy = [...markets];
    const { field, direction } = sort;
    copy.sort((a, b) => {
      const va = a[field];
      const vb = b[field];
      if (typeof va === "number" && typeof vb === "number") {
        // For edge, sort by absolute value
        if (field === "edge") {
          return direction === "desc"
            ? Math.abs(vb) - Math.abs(va)
            : Math.abs(va) - Math.abs(vb);
        }
        return direction === "desc" ? vb - va : va - vb;
      }
      const sa = String(va);
      const sb = String(vb);
      return direction === "desc"
        ? sb.localeCompare(sa)
        : sa.localeCompare(sb);
    });
    return copy;
  }, [markets, sort]);

  return { sorted, sort, toggleSort };
}
