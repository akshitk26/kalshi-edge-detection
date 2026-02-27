import { useState, useMemo } from "react";
import { useMarkets } from "./hooks/useMarkets";
import { FilterBar, useSortedMarkets } from "./components/FilterBar";
import { LookupBar } from "./components/LookupBar";
import { MarketTable } from "./components/MarketTable";
import { StatusBar } from "./components/StatusBar";
import { HedgeDashboard } from "./components/HedgeDashboard";
import type { MarketRow } from "./types/market";
import "./App.css";

type Tab = "hedge" | "scanner";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("hedge");

  // --- Scanner state (only used when tab === "scanner") ---
  const {
    markets,
    meta,
    loading,
    error,
    refresh,
    lastRefresh,
    paused,
    togglePause,
  } = useMarkets();

  const [lookupResults, setLookupResults] = useState<MarketRow[] | null>(null);
  const activeMarkets = lookupResults ?? markets;

  const [cityFilter, setCityFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");

  const filtered = useMemo(() => {
    let rows = activeMarkets;
    if (cityFilter) rows = rows.filter((m) => m.city === cityFilter);
    if (dateFilter) rows = rows.filter((m) => m.date === dateFilter);
    return rows;
  }, [activeMarkets, cityFilter, dateFilter]);

  const { sorted, sort, toggleSort } = useSortedMarkets(filtered);

  const highestEdgeTicker = useMemo(() => {
    if (sorted.length === 0) return null;
    return sorted.reduce((best, m) =>
      Math.abs(m.edge) > Math.abs(best.edge) ? m : best
    ).ticker;
  }, [sorted]);

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>AlphaCast</h1>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`sidebar-link ${activeTab === "hedge" ? "active" : ""}`}
            onClick={() => setActiveTab("hedge")}
          >
            Hedge
          </button>
          <button
            className={`sidebar-link ${activeTab === "scanner" ? "active" : ""}`}
            onClick={() => setActiveTab("scanner")}
          >
            Scanner
          </button>
        </nav>

        <div className="sidebar-footer">
          <span className="sidebar-version">v0.2</span>
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        {/* Keep both tabs mounted to preserve state, hide inactive with CSS */}
        <div style={{ display: activeTab === "hedge" ? "block" : "none", height: "100%", overflowY: "auto" }}>
          <HedgeDashboard />
        </div>

        <div style={{ display: activeTab === "scanner" ? "flex" : "none", flexDirection: "column", height: "100%", overflowY: "auto" }}>
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
            paused={paused}
            onTogglePause={togglePause}
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
                Showing lookup results ·{" "}
                <button
                  className="lookup-clear-inline"
                  onClick={() => setLookupResults(null)}
                >
                  back to all markets
                </button>
              </span>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
