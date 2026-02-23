import { useState, useEffect, useCallback, useRef } from "react";
import type {
    HedgeGroup,
    HedgeGroupsResponse,
    HedgeResult,
    HedgeCalculateResponse,
} from "../types/hedge";

const API_BASE = "/api";
const DEFAULT_INTERVAL = 30_000;

interface UseHedgeGroupsResult {
    groups: HedgeGroup[];
    loading: boolean;
    error: string | null;
    refresh: () => void;
    lastRefresh: Date | null;
    calculateAllocation: (
        groupId: string,
        budget: number,
        fee: number,
        selectedTickers?: string[]
    ) => Promise<HedgeResult | null>;
}

export function useHedgeGroups(): UseHedgeGroupsResult {
    const [groups, setGroups] = useState<HedgeGroup[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchGroups = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const res = await fetch(`${API_BASE}/hedge-groups`);
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.error || `HTTP ${res.status}`);
            }
            const data: HedgeGroupsResponse = await res.json();
            setGroups(data.groups);
            setLastRefresh(new Date());
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
        } finally {
            setLoading(false);
        }
    }, []);

    const calculateAllocation = useCallback(
        async (
            groupId: string,
            budget: number,
            fee: number,
            selectedTickers?: string[]
        ): Promise<HedgeResult | null> => {
            try {
                const params = new URLSearchParams({
                    budget: budget.toString(),
                    fee: fee.toString(),
                });
                if (selectedTickers && selectedTickers.length > 0) {
                    params.set("selected", selectedTickers.join(","));
                }
                const res = await fetch(
                    `${API_BASE}/hedge-groups/${groupId}/calculate?${params}`
                );
                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    throw new Error(body.error || `HTTP ${res.status}`);
                }
                const data: HedgeCalculateResponse = await res.json();
                return data.allocation;
            } catch (err) {
                console.error("Calculate error:", err);
                return null;
            }
        },
        []
    );

    // Initial fetch
    useEffect(() => {
        fetchGroups();
    }, [fetchGroups]);

    // Auto-refresh
    useEffect(() => {
        intervalRef.current = setInterval(fetchGroups, DEFAULT_INTERVAL);
        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, [fetchGroups]);

    return {
        groups,
        loading,
        error,
        refresh: fetchGroups,
        lastRefresh,
        calculateAllocation,
    };
}
