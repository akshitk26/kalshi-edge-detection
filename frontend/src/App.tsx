import { useState, useMemo } from "react";
import { useMarkets } from "./hooks/useMarkets";
import { FilterBar, useSortedMarkets } from "./components/FilterBar";
import { MarketTable } from "./components/MarketTable";
import { StatusBar } from "./components/StatusBar";
import "./App.css";

export default function App() {
  const { markets, meta, loading, error, refresh, lastRefresh } =
    useMarkets(/* no auto-refresh; manual only */);

  // Filters
  const [cityFilter, setCityFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");

  const filtered = useMemo(() => {
    let rows = markets;
    if (cityFilter) rows = rows.filter((m) => m.city === cityFilter);
    if (dateFilter) rows = rows.filter((m) => m.date === dateFilter);
    return rows;
  }, [markets, cityFilter, dateFilter]);

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
        <h1>Edge Engine</h1>
        <span className="app-subtitle">Weather Market Scanner</span>
      </header>

      <FilterBar
        markets={markets}
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
        total={markets.length}
        filtered={sorted.length}
        loading={loading}
        error={error}
      />
    </div>
  );
}
