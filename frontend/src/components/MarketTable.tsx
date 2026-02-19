import { useState } from "react";
import type { MarketRow, SortConfig, SortField } from "../types/market";

interface MarketTableProps {
  markets: MarketRow[];
  sort: SortConfig;
  onSort: (field: SortField) => void;
  highestEdgeTicker: string | null;
}

const COLUMNS: { label: string; field: SortField; align: "left" | "right" }[] =
  [
    { label: "Ticker", field: "ticker", align: "left" },
    { label: "Mkt %", field: "marketPrice", align: "right" },
    { label: "Fair %", field: "fairProbability", align: "right" },
    { label: "Edge %", field: "edge", align: "right" },
    { label: "Action", field: "action", align: "left" },
    { label: "Vol", field: "volume", align: "right" },
  ];

function edgeClass(edge: number): string {
  if (edge > 0) return "val-pos";
  if (edge < 0) return "val-neg";
  return "val-neutral";
}

function actionClass(action: string): string {
  if (action === "BUY YES") return "action-yes";
  if (action === "BUY NO") return "action-no";
  return "action-hold";
}

function SortIndicator({
  field,
  sort,
}: {
  field: SortField;
  sort: SortConfig;
}) {
  if (sort.field !== field) return <span className="sort-indicator">⇅</span>;
  return (
    <span className="sort-indicator active">
      {sort.direction === "desc" ? "▼" : "▲"}
    </span>
  );
}

export function MarketTable({
  markets,
  sort,
  onSort,
  highestEdgeTicker,
}: MarketTableProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleSelect = (ticker: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  if (markets.length === 0) {
    return <div className="empty-state">No markets match current filters.</div>;
  }

  return (
    <div className="table-wrapper">
      <table className="market-table">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.field}
                className={`col-${col.align}`}
                onClick={() => onSort(col.field)}
              >
                {col.label}
                <SortIndicator field={col.field} sort={sort} />
              </th>
            ))}
            <th className="col-left">Liq</th>
            <th className="col-left">Reasoning</th>
            <th className="col-left">Link</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((m) => {
            const isHighest = m.ticker === highestEdgeTicker;
            const isSelected = selected.has(m.ticker);
            const rowClass = [
              isHighest ? "row-highlight" : "",
              isSelected ? "row-selected" : "",
            ]
              .filter(Boolean)
              .join(" ") || undefined;
            return (
              <tr
                key={m.ticker}
                className={rowClass}
                onClick={() => toggleSelect(m.ticker)}
              >
                <td className="col-ticker" title={m.question}>
                  {m.ticker}
                </td>
                <td className="col-right mono">{m.marketPrice.toFixed(1)}</td>
                <td className="col-right mono">{m.fairProbability.toFixed(1)}</td>
                <td className={`col-right mono ${edgeClass(m.edge)}`}>
                  {m.edge > 0 ? "+" : ""}
                  {m.edge.toFixed(1)}
                </td>
                <td className={`col-action ${actionClass(m.action)}`}>
                  {m.action}
                </td>
                <td className="col-right mono">
                  {m.volume.toLocaleString()}
                </td>
                <td className="col-center">
                  {m.hasLiquidity ? (
                    <span className="liq-ok">✓</span>
                  ) : (
                    <span className="liq-warn">LOW</span>
                  )}
                </td>
                <td className="col-reasoning" title={m.reasoning}>
                  {m.reasoning}
                </td>
                <td>
                  <a
                    href={m.resolutionUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="link-btn"
                  >
                    Kalshi ↗
                  </a>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
