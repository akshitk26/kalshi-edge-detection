import { useState, useEffect } from "react";
import type { HedgeGroup, HedgeResult } from "../types/hedge";

interface HedgeGroupCardProps {
    group: HedgeGroup;
    budget: number;
    fee: number;
    onCalculate: (
        groupId: string,
        budget: number,
        fee: number,
        selected?: string[]
    ) => Promise<HedgeResult | null>;
}

export function HedgeGroupCard({
    group,
    budget,
    fee,
    onCalculate,
}: HedgeGroupCardProps) {
    const [result, setResult] = useState<HedgeResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(
        new Set(group.buckets.map((b) => b.ticker))
    );
    const [expanded, setExpanded] = useState(false);

    // Recalculate when budget, fee, or selection changes
    useEffect(() => {
        if (budget <= 0) return;
        let cancelled = false;
        setLoading(true);

        const selectedArr =
            selected.size === group.buckets.length
                ? undefined
                : Array.from(selected);

        onCalculate(group.groupId, budget, fee, selectedArr).then((r) => {
            if (!cancelled) {
                setResult(r);
                setLoading(false);
            }
        });

        return () => {
            cancelled = true;
        };
    }, [budget, fee, selected, group.groupId, group.buckets.length, onCalculate]);

    const toggleBucket = (ticker: string) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(ticker)) {
                if (next.size > 1) next.delete(ticker);
            } else {
                next.add(ticker);
            }
            return next;
        });
    };

    const formatDate = (d: string) => {
        // "26FEB24" → "Feb 26"
        const match = d.match(/^(\d{2})([A-Z]{3})(\d{2})$/);
        if (!match) return d;
        const months: Record<string, string> = {
            JAN: "Jan", FEB: "Feb", MAR: "Mar", APR: "Apr", MAY: "May", JUN: "Jun",
            JUL: "Jul", AUG: "Aug", SEP: "Sep", OCT: "Oct", NOV: "Nov", DEC: "Dec",
        };
        return `${months[match[2]] || match[2]} ${parseInt(match[1])}`;
    };

    const overroundClass =
        group.overround > 5
            ? "overround-high"
            : group.overround > 0
                ? "overround-mid"
                : "overround-none";

    return (
        <div className={`hedge-card ${expanded ? "expanded" : ""}`}>
            <div className="hedge-card-header" onClick={() => setExpanded(!expanded)}>
                <div className="hedge-card-title">
                    <h3>
                        {group.city}
                        <span className="hedge-type-badge">
                            {group.marketType.toUpperCase()}
                        </span>
                    </h3>
                    <span className="hedge-date">{formatDate(group.date)}</span>
                </div>
                <div className="hedge-card-badges">
                    <span className={`overround-badge ${overroundClass}`}>
                        {group.overround > 0 ? "+" : ""}
                        {group.overround.toFixed(1)}% overround
                    </span>
                    <span className="bucket-count">{group.numBuckets} buckets</span>
                    {!group.allHaveLiquidity && (
                        <span className="liq-badge-warn">⚠ Low liq</span>
                    )}
                </div>
                <span className="expand-arrow">{expanded ? "▼" : "▶"}</span>
            </div>

            {expanded && (
                <div className="hedge-card-body">
                    {/* Bucket table */}
                    <table className="bucket-table">
                        <thead>
                            <tr>
                                <th className="col-check"></th>
                                <th className="col-left">Range</th>
                                <th className="col-right">YES ¢</th>
                                <th className="col-right">NO ¢</th>
                                {result && (
                                    <>
                                        <th className="col-right">Contracts</th>
                                        <th className="col-right">Cost</th>
                                        <th className="col-right">If NO ✓</th>
                                        <th className="col-right">If YES ✗</th>
                                    </>
                                )}
                                <th className="col-center">Liq</th>
                                <th className="col-left">Link</th>
                            </tr>
                        </thead>
                        <tbody>
                            {group.buckets.map((b, i) => {
                                const alloc = result?.allocations?.[i];
                                const isSelected = selected.has(b.ticker);

                                return (
                                    <tr
                                        key={b.ticker}
                                        className={isSelected ? "" : "row-excluded"}
                                    >
                                        <td className="col-check">
                                            <input
                                                type="checkbox"
                                                checked={isSelected}
                                                onChange={() => toggleBucket(b.ticker)}
                                            />
                                        </td>
                                        <td className="col-left">{b.rangeLabel}</td>
                                        <td className="col-right mono">{b.yesPrice}</td>
                                        <td className="col-right mono">{b.noPrice}</td>
                                        {result && alloc && (
                                            <>
                                                <td className="col-right mono">{alloc.contracts}</td>
                                                <td className="col-right mono">
                                                    ${alloc.cost.toFixed(2)}
                                                </td>
                                                <td className="col-right mono val-pos">
                                                    +${alloc.profitIfNoWins.toFixed(2)}
                                                </td>
                                                <td className="col-right mono val-neg">
                                                    -${Math.abs(alloc.lossIfYesWins).toFixed(2)}
                                                </td>
                                            </>
                                        )}
                                        <td className="col-center">
                                            {b.hasLiquidity ? (
                                                <span className="liq-ok">✓</span>
                                            ) : (
                                                <span className="liq-warn">LOW</span>
                                            )}
                                        </td>
                                        <td>
                                            <a
                                                href={b.kalshiUrl}
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

                    {/* Allocation summary */}
                    {result && (
                        <div className="hedge-summary">
                            <div className="summary-grid">
                                <div className="summary-item">
                                    <span className="summary-label">Total Cost</span>
                                    <span className="summary-value">
                                        ${result.totalCost.toFixed(2)}
                                    </span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Fees</span>
                                    <span className="summary-value">
                                        ${result.totalFees.toFixed(2)}
                                    </span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Expected P&L</span>
                                    <span
                                        className={`summary-value ${result.expectedProfit >= 0 ? "val-pos" : "val-neg"}`}
                                    >
                                        {result.expectedProfit >= 0 ? "+" : ""}$
                                        {result.expectedProfit.toFixed(2)}
                                    </span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Win Rate</span>
                                    <span className="summary-value">
                                        {result.winProbability.toFixed(0)}%
                                    </span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Best Case</span>
                                    <span className="summary-value val-pos">
                                        +${result.bestCasePnl.toFixed(2)}
                                    </span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Worst Case</span>
                                    <span className="summary-value val-neg">
                                        ${result.worstCasePnl.toFixed(2)}
                                    </span>
                                </div>
                            </div>

                            {/* Scenario breakdown */}
                            <details className="scenarios-details">
                                <summary>
                                    Scenario Breakdown ({result.scenarios.length} outcomes)
                                </summary>
                                <table className="scenario-table">
                                    <thead>
                                        <tr>
                                            <th className="col-left">If this wins…</th>
                                            <th className="col-right">Net P&L</th>
                                            <th className="col-center">Result</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {result.scenarios.map((s) => (
                                            <tr key={s.winningBucket}>
                                                <td className="col-left">{s.winningLabel}</td>
                                                <td
                                                    className={`col-right mono ${s.isProfitable ? "val-pos" : "val-neg"}`}
                                                >
                                                    {s.netPnl >= 0 ? "+" : ""}${s.netPnl.toFixed(2)}
                                                </td>
                                                <td className="col-center">
                                                    {s.isProfitable ? "✅" : "❌"}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </details>
                        </div>
                    )}

                    {loading && <div className="card-loading">Calculating…</div>}
                </div>
            )}
        </div>
    );
}
