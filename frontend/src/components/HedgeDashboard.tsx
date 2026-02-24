import { useState, useEffect, useMemo } from "react";
import { useHedgeGroups } from "../hooks/useHedgeGroups";
import { BudgetInput } from "./BudgetInput";
import { HedgeGroupCard } from "./HedgeGroupCard";
import type { HedgeGroup } from "../types/hedge";

const LS_BUDGET = "alphacast_budget";
const LS_FEE = "alphacast_fee";

/** Group hedge groups by city. */
function groupByCity(groups: HedgeGroup[]): Map<string, HedgeGroup[]> {
    const map = new Map<string, HedgeGroup[]>();
    for (const g of groups) {
        const list = map.get(g.city) || [];
        list.push(g);
        map.set(g.city, list);
    }
    // Sort dates within each city
    for (const [, list] of map) {
        list.sort((a, b) => a.date.localeCompare(b.date));
    }
    return map;
}

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

    useEffect(() => {
        localStorage.setItem(LS_BUDGET, budget.toString());
    }, [budget]);

    useEffect(() => {
        localStorage.setItem(LS_FEE, fee.toString());
    }, [fee]);

    // Temporarily filter to Chicago only
    const filtered = useMemo(
        () => groups.filter((g) => g.city === "Chicago"),
        [groups]
    );

    // Group by city
    const cityMap = useMemo(() => groupByCity(filtered), [filtered]);

    // Sort cities by best overround
    const sortedCities = useMemo(() => {
        return Array.from(cityMap.entries()).sort(([, a], [, b]) => {
            const bestA = Math.max(...a.map((g) => g.overround));
            const bestB = Math.max(...b.map((g) => g.overround));
            return bestB - bestA;
        });
    }, [cityMap]);

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
                    {sortedCities.length} {sortedCities.length === 1 ? "city" : "cities"}
                    {" · "}
                    {filtered.length} date{filtered.length !== 1 ? "s" : ""}
                    {lastRefresh && (
                        <>
                            {" · Updated "}
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

            {!loading && sortedCities.length === 0 && (
                <div className="empty-state">
                    No weather markets found. Markets may be closed.
                </div>
            )}

            <div className="city-sections">
                {sortedCities.map(([city, cityGroups]) => (
                    <div className="city-section" key={city}>
                        <div className="city-section-header">
                            <h2>{city}</h2>
                            <span className="city-meta">
                                {cityGroups[0].marketType.toUpperCase()} ·{" "}
                                {cityGroups.length} date{cityGroups.length !== 1 ? "s" : ""}
                            </span>
                        </div>

                        <div className="city-dates">
                            {cityGroups.map((group) => (
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
                ))}
            </div>
        </div>
    );
}
