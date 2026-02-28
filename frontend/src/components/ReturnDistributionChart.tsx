import { useMemo, useState } from "react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell
} from "recharts";
import type { Scenario } from "../types/hedge";

interface ReturnDistributionChartProps {
    scenarios: Scenario[];
    totalOutlay: number;
}

const NUM_SIMULATIONS = 2000;
const BIN_SIZE_PCT = 3;

function runSimulation(scenarios: Scenario[], outOf: number = 2000) {
    const results: number[] = [];
    const variance = 0.4;

    for (let i = 0; i < outOf; i++) {
        const noise = scenarios.map(() => (Math.random() - 0.5) * 2 * variance);
        let variedProbs = scenarios.map((s, idx) => s.probability + noise[idx]);
        variedProbs = variedProbs.map(p => Math.max(0.001, p));
        const total = variedProbs.reduce((a, b) => a + b, 0);
        variedProbs = variedProbs.map(p => p / total);
        
        let cumulative = 0;
        const cumProbs = scenarios.map((s, idx) => {
            cumulative += variedProbs[idx];
            return { ...s, cumProb: cumulative };
        });

        const rand = Math.random();
        const winningScenario = cumProbs.find(s => rand <= s.cumProb) || cumProbs[cumProbs.length - 1];
        const randomPnlOffset = (Math.random() - 0.5) * (Math.abs(winningScenario.netPnl) * 0.15);
        results.push(winningScenario.netPnl + randomPnlOffset);
    }
    return results;
}

export function ReturnDistributionChart({ scenarios, totalOutlay }: ReturnDistributionChartProps) {
    const [, setSimTrigger] = useState(0);

    const data = useMemo(() => {
        if (!totalOutlay || scenarios.length === 0) return [];

        // 1. Run Monte Carlo simulation (100 runs)
        const simPnls = runSimulation(scenarios, NUM_SIMULATIONS);

        // 2. Force min/max bins to -100% and +100% for all cities
        const minBin = -100;
        const maxBin = 100;

        // Initialize all bins with 0 to enforce correct X-axis spacing
        const binCounts: Record<number, number> = {};
        for (let b = minBin; b <= maxBin; b += BIN_SIZE_PCT) {
            binCounts[b] = 0;
        }

        // 3. Populate bin counts from simulation
        for (const pnl of simPnls) {
            const returnPct = (pnl / totalOutlay) * 100;
            const bin = Math.floor(returnPct / BIN_SIZE_PCT) * BIN_SIZE_PCT;
            if (binCounts[bin] !== undefined) {
                binCounts[bin] += 1;
            }
        }

        // 4. Convert to array for Recharts
        const chartData = Object.entries(binCounts).map(([binStr, count]) => {
            const binNum = parseInt(binStr, 10);
            return {
                returnBin: binNum,
                displayLabel: `${binNum}%`,
                frequency: count,
                isPositive: binNum >= 0
            };
        });

        // 5. Sort by return bin (X-axis order)
        return chartData.sort((a, b) => a.returnBin - b.returnBin);
    }, [scenarios, totalOutlay]);

    if (data.length === 0) return null;

    return (
        <div className="return-distribution-chart">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h4 className="chart-title" style={{ marginBottom: 0 }}>Return Distribution</h4>
                <button
                    onClick={() => setSimTrigger(prev => prev + 1)}
                    style={{
                        background: 'transparent',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-secondary)',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        cursor: 'pointer'
                    }}
                >
                    Rerun Simulation
                </button>
            </div>
            <div style={{ width: "100%", height: 200, position: "relative" }}>
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                        data={data}
                        margin={{ top: 10, right: 30, left: 0, bottom: 20 }}
                        barCategoryGap="2%" // Tighter gap for histogram look
                        // Lock axes and labels so they never change
                    >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2e353e" />
                        <XAxis
                            dataKey="displayLabel"
                            tick={{ fontSize: 10, fill: "#5f666f" }}
                            stroke="#2e353e"
                            label={{ value: 'Return % (Approx)', position: 'bottom', offset: 0, fill: "#5f666f", fontSize: 10 }}
                            allowDataOverflow={false}
                            // Lock X axis range
                            domain={[-100, 100]}
                        />
                        <YAxis
                            tick={{ fontSize: 10, fill: "#5f666f" }}
                            tickFormatter={(val) => `${val}`} // Just frequency number
                            label={{ value: 'Frequency (out of 1000)', angle: -90, position: 'center', fill: "#5f666f", fontSize: 12, offset: 30 }}
                            stroke="#2e353e"
                            domain={[0, 1000]}
                            allowDataOverflow={false}
                            // Prevent axis from changing
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: "#1c2127",
                                border: "1px solid #2e353e",
                                borderRadius: "4px",
                                fontSize: "12px",
                                color: "#d4d8de"
                            }}
                            cursor={{ fill: 'rgba(255, 255, 255, 0.05)' }}
                            formatter={(value) => {
                                return [`${value ?? 0}`, "Frequency"];
                            }}
                            labelFormatter={(label) => `Return Range: ~${label}`}
                        />
                        <Bar dataKey="frequency" radius={[4, 4, 0, 0]}>
                            {data.map((entry, index) => (
                                <Cell
                                    key={`cell-${index}`}
                                    fill={entry.isPositive ? "#4a9e6e" : "#c05555"}
                                    fillOpacity={0.85}
                                />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
