import { useState, useEffect } from "react";
import { useHedgeGroups } from "../hooks/useHedgeGroups";
import { BudgetInput } from "./BudgetInput";
import { HedgeGroupCard } from "./HedgeGroupCard";

const LS_BUDGET = "alphacast_budget";
const LS_FEE = "alphacast_fee";

export function HedgeDashboard() {
    const { groups, loading, error, refresh, lastRefresh, calculateAllocation } =
        useHedgeGroups();

    const [budget, setBudget] = useState(() => {
        const saved = localStorage.getItem(LS_BUDGET);
        return saved ? parseFloat(saved) : 100;
    });

    const [fee, setFee] = useState(() => {
        const saved = localStorage.getItem(LS_FEE);
        return saved ? parseFloat(saved) : 0.011;
    });

    // Persist to localStorage
    useEffect(() => {
        localStorage.setItem(LS_BUDGET, budget.toString());
    }, [budget]);

    useEffect(() => {
        localStorage.setItem(LS_FEE, fee.toString());
    }, [fee]);

    // Sort groups: highest overround first
    const sorted = [...groups].sort((a, b) => b.overround - a.overround);

    return (
        <div className="hedge-dashboard">
            <BudgetInput
                budget={budget}
                fee={fee}
                onBudgetChange={setBudget}
                onFeeChange={setFee}
            />

            <div className="hedge-meta-row">
                <span className="hedge-meta">
                    {sorted.length} opportunities
                    {lastRefresh && (
                        <>
                            {" "}
                            · Updated{" "}
                            {lastRefresh.toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                            })}
                        </>
                    )}
                </span>
                <button className="refresh-btn" onClick={refresh} disabled={loading}>
                    {loading ? "⟳" : "↻"} Refresh
                </button>
            </div>

            {error && <div className="hedge-error">⚠ {error}</div>}

            {!loading && sorted.length === 0 && (
                <div className="empty-state">
                    No weather markets found. Markets may be closed.
                </div>
            )}

            <div className="hedge-cards">
                {sorted.map((group) => (
                    <HedgeGroupCard
                        key={group.groupId}
                        group={group}
                        budget={budget}
                        fee={fee}
                        onCalculate={calculateAllocation}
                    />
                ))}
            </div>
        </div>
    );
}
