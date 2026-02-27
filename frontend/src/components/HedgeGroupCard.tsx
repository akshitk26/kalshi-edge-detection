import { useState, useEffect, useCallback, useMemo } from "react";
import type { HedgeGroup, HedgeResult, BucketAllocation, Scenario } from "../types/hedge";
import { ReturnDistributionChart } from "./ReturnDistributionChart";

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

/**
 * Locally recalculates allocations + scenarios from user-edited quantities.
 * This mirrors the backend logic but runs instantly.
 */
function recalcLocal(
    group: HedgeGroup,
    baseResult: HedgeResult,
    overrides: Record<string, number>,
    feePerContract: number,
): HedgeResult {
    const allocations: BucketAllocation[] = baseResult.allocations.map((a) => {
        const qty = overrides[a.ticker] ?? a.contracts;
        const costDollars = qty * a.noPrice / 100;
        const feeDollars = qty * feePerContract;
        const totalOutlay = costDollars + feeDollars;
        const profitIfNoWins = qty * (100 - a.noPrice) / 100 - feeDollars;
        const lossIfYesWins = -(costDollars + feeDollars);
        return { ...a, contracts: qty, cost: costDollars, fees: feeDollars, totalOutlay, profitIfNoWins, lossIfYesWins };
    });

    const included = allocations.filter(a => a.included && a.contracts > 0);
    const totalCost = included.reduce((s, a) => s + a.cost, 0);
    const totalFees = included.reduce((s, a) => s + a.fees, 0);
    const totalOutlay = totalCost + totalFees;
    const totalContracts = included.reduce((s, a) => s + a.contracts, 0);

    const sumYes = group.sumYesPrices || 1;
    const scenarios: Scenario[] = group.buckets.map((b) => {
        const prob = b.yesPrice / sumYes;
        let netPnl = 0;
        for (const a of included) {
            if (a.ticker === b.ticker) {
                netPnl += a.lossIfYesWins;
            } else {
                netPnl += a.profitIfNoWins;
            }
        }
        return {
            winningBucket: b.ticker,
            winningLabel: b.rangeLabel,
            probability: prob,
            netPnl: Math.round(netPnl * 100) / 100,
            isProfitable: netPnl > 0,
        };
    });

    const expectedProfit = scenarios.reduce((s, sc) => s + sc.probability * sc.netPnl, 0);
    const winProbability = scenarios.filter(s => s.isProfitable).reduce((s, sc) => s + sc.probability, 0) * 100;
    const pnls = scenarios.map(s => s.netPnl);
    const worstCasePnl = Math.min(...pnls);
    const bestCasePnl = Math.max(...pnls);
    const feeCostRatio = totalCost > 0 ? totalFees / totalCost : 0;

    return {
        ...baseResult,
        allocations,
        scenarios,
        totalCost: Math.round(totalCost * 100) / 100,
        totalFees: Math.round(totalFees * 100) / 100,
        totalOutlay: Math.round(totalOutlay * 100) / 100,
        expectedProfit: Math.round(expectedProfit * 100) / 100,
        worstCasePnl: Math.round(worstCasePnl * 100) / 100,
        bestCasePnl: Math.round(bestCasePnl * 100) / 100,
        winProbability: Math.round(winProbability * 10) / 10,
        totalContracts,
        feeCostRatio: Math.round(feeCostRatio * 100) / 100,
    };
}

export function HedgeGroupCard({
    group,
    budget,
    fee,
    onCalculate,
}: HedgeGroupCardProps) {
    const [baseResult, setBaseResult] = useState<HedgeResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(
        new Set(group.buckets.map((b) => b.ticker))
    );
    const [expanded, setExpanded] = useState(false);
    const [showMath, setShowMath] = useState(false);
    const [qtyOverrides, setQtyOverrides] = useState<Record<string, number>>({});

    // Fetch base allocation from backend
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
                setBaseResult(r);
                setQtyOverrides({}); // reset overrides when base changes
                setLoading(false);
            }
        });

        return () => { cancelled = true; };
    }, [budget, fee, selected, group.groupId, group.buckets.length, onCalculate]);

    // Compute result: if user has overrides, recalculate locally
    const result = useMemo(() => {
        if (!baseResult) return null;
        if (Object.keys(qtyOverrides).length === 0) return baseResult;
        return recalcLocal(group, baseResult, qtyOverrides, baseResult.feePerContract);
    }, [baseResult, qtyOverrides, group]);

    const handleQtyChange = useCallback((ticker: string, value: string) => {
        const num = parseInt(value, 10);
        if (isNaN(num) || num < 0) {
            setQtyOverrides(prev => {
                const next = { ...prev };
                delete next[ticker];
                return next;
            });
            return;
        }
        setQtyOverrides(prev => ({ ...prev, [ticker]: num }));
    }, []);

    const resetOverrides = useCallback(() => setQtyOverrides({}), []);

    const hasOverrides = Object.keys(qtyOverrides).length > 0;

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
        const match = d.match(/^(\d{2})([A-Z]{3})(\d{2})$/);
        if (!match) return d;
        const months: Record<string, string> = {
            JAN: "Jan", FEB: "Feb", MAR: "Mar", APR: "Apr", MAY: "May", JUN: "Jun",
            JUL: "Jul", AUG: "Aug", SEP: "Sep", OCT: "Oct", NOV: "Nov", DEC: "Dec",
        };
        return `${months[match[2]] || match[2]} ${parseInt(match[3])}`;
    };

    const overroundClass =
        group.overround > 5
            ? "overround-high"
            : group.overround > 0
                ? "overround-mid"
                : "overround-none";

    const qualityClass = result ? `quality-${result.quality}` : "";
    const qualityLabel = result
        ? { good: "Good opportunity", fair: "Fair", poor: "Poor opportunity" }[result.quality]
        : "";

    const filledAllocs = result?.allocations.filter(a => a.included && a.contracts > 0) ?? [];
    const bestScenario = result?.scenarios.reduce((a, b) => a.netPnl > b.netPnl ? a : b);
    const worstScenario = result?.scenarios.reduce((a, b) => a.netPnl < b.netPnl ? a : b);

    return (
        <div className={`hedge-card ${expanded ? "expanded" : ""}`}>
            <div className="hedge-card-header" onClick={() => setExpanded(!expanded)}>
                <div className="hedge-card-title">
                    <span className="hedge-date">{formatDate(group.date)}</span>
                    <span className="hedge-type-badge">
                        {group.marketType.toUpperCase()}
                    </span>
                    {result && (
                        <span className={`quality-badge ${qualityClass}`}>
                            {qualityLabel}
                        </span>
                    )}
                    {loading && !result && (
                        <span className="loading-dot" />
                    )}
                </div>
                <div className="hedge-card-badges">
                    <span className={`overround-badge ${overroundClass}`}>
                        {group.overround > 0 ? "+" : ""}
                        {group.overround.toFixed(1)}% overround
                    </span>
                    <span className="bucket-count">{group.numBuckets} buckets</span>
                    {!group.allHaveLiquidity && (
                        <span className="liq-badge-warn">Low liq</span>
                    )}
                </div>
                <span className="expand-arrow">{expanded ? "v" : ">"}</span>
            </div>

            {expanded && (
                <div className="hedge-card-body">
                    {result && result.quality === "poor" && result.qualityReason && (
                        <div className="quality-warning">
                            {result.qualityReason}
                        </div>
                    )}

                    <table className="bucket-table">
                        <thead>
                            <tr>
                                <th className="col-check"></th>
                                <th className="col-left">Range</th>
                                <th className="col-right">YES c</th>
                                <th className="col-right">NO c</th>
                                {result && (
                                    <>
                                        <th className="col-right">Qty</th>
                                        <th className="col-right">Outlay</th>
                                        <th className="col-right">If NO wins</th>
                                        <th className="col-right">If YES wins</th>
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
                                                <td className="col-right">
                                                    <input
                                                        type="number"
                                                        className="qty-input"
                                                        min={0}
                                                        value={qtyOverrides[b.ticker] ?? alloc.contracts}
                                                        onChange={(e) => handleQtyChange(b.ticker, e.target.value)}
                                                        onClick={(e) => e.stopPropagation()}
                                                    />
                                                </td>
                                                <td className="col-right mono">
                                                    {alloc.totalOutlay > 0 ? `$${alloc.totalOutlay.toFixed(2)}` : "-"}
                                                </td>
                                                <td className="col-right mono val-pos">
                                                    {alloc.profitIfNoWins > 0 ? `+$${alloc.profitIfNoWins.toFixed(2)}` : "-"}
                                                </td>
                                                <td className="col-right mono val-neg">
                                                    {alloc.lossIfYesWins < 0 ? `-$${Math.abs(alloc.lossIfYesWins).toFixed(2)}` : "-"}
                                                </td>
                                            </>
                                        )}
                                        <td className="col-center">
                                            {b.hasLiquidity ? (
                                                <span className="liq-ok">OK</span>
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
                                                Kalshi
                                            </a>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>

                    {/* Summary */}
                    {result && (
                        <div className="hedge-summary">
                            {hasOverrides && (
                                <div className="override-banner">
                                    Custom quantities active
                                    <button className="override-reset" onClick={resetOverrides}>
                                        Reset to auto
                                    </button>
                                </div>
                            )}

                            <div className="summary-grid">
                                <div className="summary-item">
                                    <span className="summary-label">Total Outlay</span>
                                    <span className="summary-value">
                                        ${result.totalOutlay.toFixed(2)}
                                    </span>
                                    <span className="summary-sub">
                                        ${result.totalCost.toFixed(2)} cost + ${result.totalFees.toFixed(2)} fees
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
                                    <span className="summary-sub">prob-weighted</span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Win Prob</span>
                                    <span className="summary-value">
                                        {result.winProbability.toFixed(0)}%
                                    </span>
                                    <span className="summary-sub">market-implied</span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Best Case</span>
                                    <span className="summary-value val-pos">
                                        +${result.bestCasePnl.toFixed(2)}
                                    </span>
                                    <span className="summary-sub">
                                        {bestScenario ? `${(bestScenario.probability * 100).toFixed(0)}% likely` : ""}
                                    </span>
                                </div>
                                <div className="summary-item">
                                    <span className="summary-label">Worst Case</span>
                                    <span className="summary-value val-neg">
                                        ${result.worstCasePnl.toFixed(2)}
                                    </span>
                                    <span className="summary-sub">
                                        {worstScenario ? `${(worstScenario.probability * 100).toFixed(0)}% likely` : ""}
                                    </span>
                                </div>
                            </div>

                            <ReturnDistributionChart
                                scenarios={result.scenarios}
                                totalOutlay={result.totalOutlay}
                            />

                            <button
                                className="show-math-btn"
                                onClick={() => setShowMath(!showMath)}
                            >
                                {showMath ? "Hide math" : "Show math"}
                            </button>

                            {showMath && (
                                <div className="math-panel">
                                    {/* Positions */}
                                    <div className="math-section">
                                        <h4 className="math-heading">Positions</h4>
                                        <div className="math-rows">
                                            {filledAllocs.map(a => (
                                                <div className="math-row" key={a.ticker}>
                                                    <span className="math-label">{a.rangeLabel}</span>
                                                    <span className="math-detail">
                                                        {a.contracts} NO @ {a.noPrice}c
                                                    </span>
                                                    <span className="math-eq">=</span>
                                                    <span className="math-val">${a.cost.toFixed(2)} cost</span>
                                                    <span className="math-val-sub">+ ${a.fees.toFixed(2)} fees</span>
                                                    <span className="math-eq">=</span>
                                                    <span className="math-val-bold">${a.totalOutlay.toFixed(2)}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Best case */}
                                    {bestScenario && (
                                        <div className="math-section">
                                            <h4 className="math-heading">
                                                Best case
                                                <span className="math-prob">
                                                    {(bestScenario.probability * 100).toFixed(0)}% chance
                                                </span>
                                            </h4>
                                            <p className="math-premise">
                                                If "{bestScenario.winningLabel}" wins YES:
                                            </p>
                                            <div className="math-rows">
                                                {filledAllocs.map(a => (
                                                    <div className="math-row" key={a.ticker}>
                                                        <span className="math-label">{a.rangeLabel}</span>
                                                        {a.ticker === bestScenario.winningBucket ? (
                                                            <span className="math-val val-neg">
                                                                NO loses: -${Math.abs(a.lossIfYesWins).toFixed(2)}
                                                            </span>
                                                        ) : (
                                                            <span className="math-val val-pos">
                                                                NO wins: +${a.profitIfNoWins.toFixed(2)}
                                                            </span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="math-total val-pos">
                                                Net: +${bestScenario.netPnl.toFixed(2)}
                                            </div>
                                        </div>
                                    )}

                                    {/* Worst case */}
                                    {worstScenario && (
                                        <div className="math-section">
                                            <h4 className="math-heading">
                                                Worst case
                                                <span className="math-prob">
                                                    {(worstScenario.probability * 100).toFixed(0)}% chance
                                                </span>
                                            </h4>
                                            <p className="math-premise">
                                                If "{worstScenario.winningLabel}" wins YES:
                                            </p>
                                            <div className="math-rows">
                                                {filledAllocs.map(a => (
                                                    <div className="math-row" key={a.ticker}>
                                                        <span className="math-label">{a.rangeLabel}</span>
                                                        {a.ticker === worstScenario.winningBucket ? (
                                                            <span className="math-val val-neg">
                                                                NO loses: -${Math.abs(a.lossIfYesWins).toFixed(2)}
                                                            </span>
                                                        ) : (
                                                            <span className="math-val val-pos">
                                                                NO wins: +${a.profitIfNoWins.toFixed(2)}
                                                            </span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="math-total val-neg">
                                                Net: ${worstScenario.netPnl.toFixed(2)}
                                            </div>
                                        </div>
                                    )}

                                    {/* EV explanation */}
                                    {result.scenarios.length > 0 && (
                                        <div className="math-section">
                                            <h4 className="math-heading">Expected value</h4>
                                            <div className="math-rows">
                                                {result.scenarios
                                                    .filter(s => s.probability > 0.01)
                                                    .map(s => (
                                                        <div className="math-row" key={s.winningBucket}>
                                                            <span className="math-label">{s.winningLabel}</span>
                                                            <span className="math-detail">
                                                                {(s.probability * 100).toFixed(0)}%
                                                            </span>
                                                            <span className="math-eq">x</span>
                                                            <span className={`math-val ${s.isProfitable ? "val-pos" : "val-neg"}`}>
                                                                {s.netPnl >= 0 ? "+" : ""}${s.netPnl.toFixed(2)}
                                                            </span>
                                                            <span className="math-eq">=</span>
                                                            <span className={`math-val ${(s.probability * s.netPnl) >= 0 ? "val-pos" : "val-neg"}`}>
                                                                {(s.probability * s.netPnl) >= 0 ? "+" : ""}$
                                                                {(s.probability * s.netPnl).toFixed(2)}
                                                            </span>
                                                        </div>
                                                    ))}
                                            </div>
                                            <div className={`math-total ${result.expectedProfit >= 0 ? "val-pos" : "val-neg"}`}>
                                                EV = {result.expectedProfit >= 0 ? "+" : ""}${result.expectedProfit.toFixed(2)}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {loading && (
                        <div className="card-skeleton">
                            <div className="skeleton-row"><div className="skeleton-bar w60" /><div className="skeleton-bar w40" /></div>
                            <div className="skeleton-row"><div className="skeleton-bar w80" /><div className="skeleton-bar w30" /></div>
                            <div className="skeleton-row"><div className="skeleton-bar w50" /><div className="skeleton-bar w50" /></div>
                            <div className="skeleton-summary">
                                <div className="skeleton-box" />
                                <div className="skeleton-box" />
                                <div className="skeleton-box" />
                                <div className="skeleton-box" />
                                <div className="skeleton-box" />
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
