import { useState, useMemo } from "react";
import type { MarketRow, SortConfig, SortField, SortDirection } from "../types/market";

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
}: FilterBarProps) {
  const cities = useMemo(() => {
    const set = new Set(markets.map((m) => m.city).filter(Boolean));
    return Array.from(set).sort();
  }, [markets]);

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
          {cities.map((c) => (
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
          <span className="meta-label">
            Updated: {lastRefresh.toLocaleTimeString()}
          </span>
        )}
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
