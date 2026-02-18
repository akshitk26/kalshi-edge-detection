import { useState } from "react";
import type { MarketRow } from "../types/market";

const API_BASE = "/api";

interface LookupBarProps {
  onResults: (rows: MarketRow[]) => void;
  onClear: () => void;
  hasResults: boolean;
}

export function LookupBar({ onResults, onClear, hasResults }: LookupBarProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLookup = async () => {
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_BASE}/lookup?q=${encodeURIComponent(q)}`
      );
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }

      onResults(data.markets);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleLookup();
  };

  const handleClear = () => {
    setQuery("");
    setError(null);
    onClear();
  };

  return (
    <div className="lookup-bar">
      <label className="lookup-label">Lookup</label>
      <input
        className="lookup-input"
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Paste Kalshi URL, ticker, or series (e.g. KXHIGHNY, KXHIGHTATL-26FEB18-B65.5)"
        spellCheck={false}
      />
      <button
        className="lookup-btn"
        onClick={handleLookup}
        disabled={loading || !query.trim()}
      >
        {loading ? "…" : "Analyze"}
      </button>
      {hasResults && (
        <button className="lookup-btn lookup-clear" onClick={handleClear}>
          Clear
        </button>
      )}
      {error && <span className="lookup-error">{error}</span>}
    </div>
  );
}
