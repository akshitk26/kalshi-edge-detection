import { useState, useMemo } from "react";
import { useMarkets } from "./hooks/useMarkets";
import { FilterBar, useSortedMarkets } from "./components/FilterBar";
import { LookupBar } from "./components/LookupBar";
import { MarketTable } from "./components/MarketTable";
import { StatusBar } from "./components/StatusBar";
import type { MarketRow } from "./types/market";
import "./App.css";

export default function App() {
  const { markets, meta, loading, error, refresh, lastRefresh } =
    useMarkets(/* no auto-refresh; manual only */);

  // Lookup overlay: when set, replaces the main table with lookup results
  const [lookupResults, setLookupResults] = useState<MarketRow[] | null>(null);

  const activeMarkets = lookupResults ?? markets;

  // Filters
  const [cityFilter, setCityFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");

  const filtered = useMemo(() => {
    let rows = activeMarkets;
    if (cityFilter) rows = rows.filter((m) => m.city === cityFilter);
    if (dateFilter) rows = rows.filter((m) => m.date === dateFilter);
    return rows;
  }, [activeMarkets, cityFilter, dateFilter]);

  // Sort
  const { sorted, sort, toggleSort } = useSortedMarkets(filtered);

  // Highlight highest absolute edge
  const highestEdgeTicker = useMemo(() => {
    if (sorted.length === 0) return null;
    return sorted.reduce((best, m) =>
      Math.abs(m.edge) > Math.abs(best.edge) ? m : best
    ).ticker;
  }, [sorted]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>AlphaCast</h1>
        <span className="app-subtitle">Weather Market Scanner</span>
      </header>

      <LookupBar
        onResults={setLookupResults}
        onClear={() => setLookupResults(null)}
        hasResults={lookupResults !== null}
      />

      <FilterBar
        markets={activeMarkets}
        selectedCity={cityFilter}
        selectedDate={dateFilter}
        onCityChange={setCityFilter}
        onDateChange={setDateFilter}
        lastRefresh={lastRefresh}
        onRefresh={refresh}
        loading={loading}
        priceSource={meta?.priceSource ?? ""}
      />

      <MarketTable
        markets={sorted}
        sort={sort}
        onSort={toggleSort}
        highestEdgeTicker={highestEdgeTicker}
      />

      <StatusBar
        total={activeMarkets.length}
        filtered={sorted.length}
        loading={loading}
        error={error}
      />
      {lookupResults !== null && (
        <div className="status-bar">
          <span className="lookup-active-hint">
            Showing lookup results · <button className="lookup-clear-inline" onClick={() => setLookupResults(null)}>back to all markets</button>
          </span>
        </div>
      )}
    </div>
  );
}
