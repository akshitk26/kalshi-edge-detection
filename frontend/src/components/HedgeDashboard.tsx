import { useState, useEffect, useMemo, useCallback } from "react";
import { useHedgeGroups } from "../hooks/useHedgeGroups";
import { HedgeGroupCard } from "./HedgeGroupCard";
import type { HedgeResult } from "../types/hedge";

const LS_BUDGET = "alphacast_budget";
const LS_FEE = "alphacast_fee";
const LS_CITY = "alphacast_city";
const LS_EXIT_THRESHOLD = "alphacast_exit_threshold";

/** Parse group date "28FEB26" (DDMMMYY) to YYYY-MM-DD for comparison. */
function groupDateToIso(dateStr: string): string | null {
    const match = dateStr.match(/^(\d{2})([A-Z]{3})(\d{2})$/);
    if (!match) return null;
    const months: Record<string, string> = {
        JAN: "01", FEB: "02", MAR: "03", APR: "04", MAY: "05", JUN: "06",
        JUL: "07", AUG: "08", SEP: "09", OCT: "10", NOV: "11", DEC: "12",
    };
    const mm = months[match[2]];
    if (!mm) return null;
    const yy = parseInt(match[3], 10);
    const yyyy = yy >= 0 && yy <= 50 ? 2000 + yy : 1900 + yy;
    return `${yyyy}-${mm}-${match[1]}`;
}

/** True if group date is today (local date). */
function isToday(dateStr: string): boolean {
    const iso = groupDateToIso(dateStr);
    if (!iso) return false;
    const today = new Date();
    const todayIso = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
    return iso === todayIso;
}

/** Almost resolved: win prob very one-sided. */
function isAlmostResolved(result: HedgeResult): boolean {
    return result.winProbability >= 95 || result.winProbability <= 5;
}

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
    const [exitThreshold, setExitThreshold] = useState(() => {
        const saved = localStorage.getItem(LS_EXIT_THRESHOLD);
        return saved ? parseFloat(saved) : 0.65;
    });
    const [budgetStr, setBudgetStr] = useState(budget.toString());
    const [feeStr, setFeeStr] = useState((fee * 100).toFixed(1));
    const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null);

    useEffect(() => { localStorage.setItem(LS_BUDGET, budget.toString()); }, [budget]);
    useEffect(() => { localStorage.setItem(LS_FEE, fee.toString()); }, [fee]);
    useEffect(() => { localStorage.setItem(LS_CITY, selectedCity); }, [selectedCity]);
    useEffect(() => { localStorage.setItem(LS_EXIT_THRESHOLD, exitThreshold.toString()); }, [exitThreshold]);
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

    // Group ALL groups by city (render all, hide non-selected with CSS)
    const cityGroupsMap = useMemo(() => {
        const map = new Map<string, typeof groups>();
        for (const g of groups) {
            const list = map.get(g.city) || [];
            list.push(g);
            map.set(g.city, list);
        }
        for (const [, list] of map) {
            list.sort((a, b) => a.date.localeCompare(b.date));
        }
        return map;
    }, [groups]);

    const cityGroups = cityGroupsMap.get(selectedCity) ?? [];
    const selectedCount = cityGroups.length;

    // Default expand first group so markets show; when its result loads, switch to next day if current is poor or almost resolved
    useEffect(() => {
        if (cityGroups.length === 0) return;
        const ids = new Set(cityGroups.map((g) => g.groupId));
        if (!expandedGroupId || !ids.has(expandedGroupId)) {
            setExpandedGroupId(cityGroups[0].groupId);
        }
    }, [selectedCity, cityGroups, expandedGroupId]);

    const handleResultLoad = useCallback((groupId: string, result: HedgeResult) => {
        setExpandedGroupId((current) => {
            if (current !== groupId) return current;
            const list = cityGroupsMap.get(selectedCity) ?? [];
            const idx = list.findIndex((g) => g.groupId === groupId);
            if (idx < 0) return current;
            const isCurrentDay = isToday(list[idx].date);
            const poorOrResolved = result.quality === "poor" || isAlmostResolved(result);
            if (isCurrentDay && poorOrResolved && list.length > 1) {
                const nextGroup = list[idx + 1];
                return nextGroup ? nextGroup.groupId : current;
            }
            return current;
        });
    }, [selectedCity, cityGroupsMap]);

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
                        {selectedCount} date{selectedCount !== 1 ? "s" : ""}
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

            {!loading && selectedCount === 0 && selectedCity && (
                <div className="empty-state">
                    No markets found for {selectedCity}. Try another city.
                </div>
            )}

            {/* ── Render ALL cities, hide non-selected (preserves state) ── */}
            {Array.from(cityGroupsMap.entries()).map(([city, cityGroupList]) => (
                <div
                    key={city}
                    className="city-dates"
                    style={{ display: city === selectedCity ? undefined : "none" }}
                >
                    {cityGroupList.map((group) => (
                        <HedgeGroupCard
                            key={group.groupId}
                            group={group}
                            budget={budget}
                            fee={fee}
                            exitThreshold={exitThreshold}
                            onExitThresholdChange={setExitThreshold}
                            onCalculate={calculateAllocation}
                            expanded={expandedGroupId === group.groupId}
                            onToggle={() => setExpandedGroupId((id) => (id === group.groupId ? null : group.groupId))}
                            onResultLoad={handleResultLoad}
                        />
                    ))}
                </div>
            ))}
        </div>
    );
}
