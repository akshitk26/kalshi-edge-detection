import { useState, useEffect, useMemo } from "react";
import { useHedgeGroups } from "../hooks/useHedgeGroups";
import { HedgeGroupCard } from "./HedgeGroupCard";

const LS_BUDGET = "alphacast_budget";
const LS_FEE = "alphacast_fee";
const LS_CITY = "alphacast_city";

/** City → state + short code. */
const CITIES: Record<string, { state: string; code: string }> = {
    "New York": { state: "NY", code: "NYC" },
    "Chicago": { state: "IL", code: "CHI" },
    "Los Angeles": { state: "CA", code: "LAX" },
    "Miami": { state: "FL", code: "MIA" },
    "Boston": { state: "MA", code: "BOS" },
    "Denver": { state: "CO", code: "DEN" },
    "Atlanta": { state: "GA", code: "ATL" },
    "Philadelphia": { state: "PA", code: "PHL" },
    "Phoenix": { state: "AZ", code: "PHX" },
};

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
    const [selectedCity, setSelectedCity] = useState(() => {
        return localStorage.getItem(LS_CITY) || "";
    });
    const [budgetStr, setBudgetStr] = useState(budget.toString());
    const [feeStr, setFeeStr] = useState((fee * 100).toFixed(1));

    useEffect(() => { localStorage.setItem(LS_BUDGET, budget.toString()); }, [budget]);
    useEffect(() => { localStorage.setItem(LS_FEE, fee.toString()); }, [fee]);
    useEffect(() => { localStorage.setItem(LS_CITY, selectedCity); }, [selectedCity]);
    useEffect(() => { setBudgetStr(budget.toString()); }, [budget]);

    const availableCities = useMemo(() => {
        const cities = new Set(groups.map(g => g.city));
        return Array.from(cities).sort();
    }, [groups]);

    useEffect(() => {
        if (!selectedCity && availableCities.length > 0) {
            setSelectedCity(availableCities[0]);
        }
    }, [availableCities, selectedCity]);

    const cityGroups = useMemo(() => {
        if (!selectedCity) return [];
        return groups
            .filter(g => g.city === selectedCity)
            .sort((a, b) => a.date.localeCompare(b.date));
    }, [groups, selectedCity]);

    const handleBudgetBlur = () => {
        const val = parseFloat(budgetStr);
        if (!isNaN(val) && val > 0) setBudget(val);
        else setBudgetStr(budget.toString());
    };
    const handleFeeBlur = () => {
        const val = parseFloat(feeStr);
        if (!isNaN(val) && val >= 0) setFee(val / 100);
        else setFeeStr((fee * 100).toFixed(1));
    };

    const info = CITIES[selectedCity];

    return (
        <div className="hedge-dashboard">
            {/* ── City tabs (trading terminal style) ── */}
            <div className="city-tabs">
                {availableCities.map(city => {
                    const ci = CITIES[city];
                    return (
                        <button
                            key={city}
                            className={`city-tab ${city === selectedCity ? "active" : ""}`}
                            onClick={() => setSelectedCity(city)}
                        >
                            <span className="city-tab-code">{ci?.code || city.slice(0, 3).toUpperCase()}</span>
                        </button>
                    );
                })}
                {loading && availableCities.length === 0 && (
                    <>
                        <div className="skeleton-tab" />
                        <div className="skeleton-tab" />
                        <div className="skeleton-tab" />
                        <div className="skeleton-tab" />
                        <div className="skeleton-tab" />
                    </>
                )}
            </div>

            {/* ── Top bar: city name + inputs ── */}
            <div className="dash-topbar">
                <div className="topbar-city">
                    <span className="city-name">{selectedCity.toUpperCase()}</span>
                    {info && <span className="city-state">{info.state}</span>}
                </div>

                <div className="topbar-controls">
                    <div className="inline-field">
                        <label htmlFor="budget-input">Budget</label>
                        <div className="input-with-prefix">
                            <span className="prefix">$</span>
                            <input
                                id="budget-input"
                                type="text"
                                inputMode="decimal"
                                value={budgetStr}
                                onChange={(e) => setBudgetStr(e.target.value)}
                                onBlur={handleBudgetBlur}
                                onKeyDown={(e) => e.key === "Enter" && handleBudgetBlur()}
                                placeholder="100"
                            />
                        </div>
                    </div>
                    <div className="inline-field">
                        <label htmlFor="fee-input">Fee</label>
                        <div className="input-with-suffix">
                            <input
                                id="fee-input"
                                type="text"
                                inputMode="decimal"
                                value={feeStr}
                                onChange={(e) => setFeeStr(e.target.value)}
                                onBlur={handleFeeBlur}
                                onKeyDown={(e) => e.key === "Enter" && handleFeeBlur()}
                                placeholder="1.1"
                            />
                            <span className="suffix">c</span>
                        </div>
                    </div>

                    <div className="topbar-meta">
                        {cityGroups.length} date{cityGroups.length !== 1 ? "s" : ""}
                        {lastRefresh && (
                            <>
                                {" · "}
                                {lastRefresh.toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                })}
                            </>
                        )}
                    </div>

                    <button className="refresh-btn" onClick={refresh} disabled={loading}>
                        Refresh
                    </button>
                </div>
            </div>

            {error && <div className="hedge-error">{error}</div>}

            {!loading && cityGroups.length === 0 && selectedCity && (
                <div className="empty-state">
                    No markets found for {selectedCity}. Try another city.
                </div>
            )}

            {/* ── Date cards ── */}
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
    );
}
