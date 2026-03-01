import { useState, useMemo, useCallback } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { usePortfolio } from "../hooks/usePortfolio";
import type {
  MarketPosition,
  TimeRange,
} from "../types/portfolio";

const TIME_RANGES: TimeRange[] = ["1D", "1W", "1M", "3M", "ALL"];

function rangeMs(range: TimeRange): number {
  switch (range) {
    case "1D":
      return 24 * 60 * 60 * 1000;
    case "1W":
      return 7 * 24 * 60 * 60 * 1000;
    case "1M":
      return 30 * 24 * 60 * 60 * 1000;
    case "3M":
      return 90 * 24 * 60 * 60 * 1000;
    case "ALL":
      return Infinity;
  }
}

function formatDollars(cents: number): string {
  const dollars = cents / 100;
  return dollars.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
}

function formatCompact(cents: number): string {
  const dollars = Math.abs(cents / 100);
  const sign = cents >= 0 ? "+" : "-";
  return `${sign}$${dollars.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatTime(ts: string, range: TimeRange): string {
  const d = new Date(ts);
  if (range === "1D") {
    return d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatTooltipTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface ChartPoint {
  ts: string;
  value: number;
  label: string;
}

export function PortfolioView() {
  const { configured, data, history, loading, error } = usePortfolio();
  const [range, setRange] = useState<TimeRange>("1W");
  const [hoverValue, setHoverValue] = useState<number | null>(null);
  const [hoverTime, setHoverTime] = useState<string | null>(null);

  const filteredHistory = useMemo(() => {
    if (history.length === 0) return [];
    const ms = rangeMs(range);
    if (ms === Infinity) return history;
    const latestEpoch = history[history.length - 1].epoch;
    const cutoffEpoch = latestEpoch - ms / 1000;
    return history.filter((s) => s.epoch >= cutoffEpoch);
  }, [history, range]);

  const chartData: ChartPoint[] = useMemo(
    () =>
      filteredHistory.map((s) => ({
        ts: s.ts,
        value: s.total_value / 100,
        label: formatTime(s.ts, range),
      })),
    [filteredHistory, range]
  );

  const { change, changePct, isPositive } = useMemo(() => {
    if (chartData.length < 2)
      return { change: 0, changePct: 0, isPositive: true };
    const first = chartData[0].value;
    const last = chartData[chartData.length - 1].value;
    const ch = last - first;
    const pct = first > 0 ? (ch / first) * 100 : 0;
    return { change: ch * 100, changePct: pct, isPositive: ch >= 0 };
  }, [chartData]);

  const displayValue =
    hoverValue !== null
      ? hoverValue * 100
      : (data?.balance.total_value ?? 0);

  const handleMouseMove = useCallback(
    (state: { activePayload?: Array<{ payload: ChartPoint }> }) => {
      if (state.activePayload?.[0]) {
        setHoverValue(state.activePayload[0].payload.value);
        setHoverTime(state.activePayload[0].payload.ts);
      }
    },
    []
  );

  const handleMouseLeave = useCallback(() => {
    setHoverValue(null);
    setHoverTime(null);
  }, []);

  if (loading) {
    return (
      <div className="portfolio-view">
        <div className="portfolio-skeleton">
          <div className="skeleton-bar w40" style={{ height: 36 }} />
          <div className="skeleton-bar w30" style={{ height: 18, marginTop: 8 }} />
          <div
            className="skeleton-bar"
            style={{ width: "100%", height: 300, marginTop: 24 }}
          />
        </div>
      </div>
    );
  }

  if (configured === false) {
    return (
      <div className="portfolio-view">
        <div className="portfolio-setup">
          <h2>Connect Your Kalshi Account</h2>
          <p>
            Add your Kalshi API key to enable portfolio tracking. Generate one
            in your Kalshi account settings under API Keys.
          </p>
          <div className="setup-steps">
            <div className="setup-step">
              <span className="step-num">1</span>
              <span>
                Go to{" "}
                <a
                  href="https://kalshi.com/account/api-keys"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Kalshi API Keys
                </a>
              </span>
            </div>
            <div className="setup-step">
              <span className="step-num">2</span>
              <span>Generate a new API key and download the private key</span>
            </div>
            <div className="setup-step">
              <span className="step-num">3</span>
              <span>
                Add to your <code>.env</code> file:
              </span>
            </div>
          </div>
          <pre className="setup-code">
{`KALSHI_API_KEY_ID=your-key-uuid
KALSHI_PRIVATE_KEY_PATH=~/.kalshi/private_key.pem`}
          </pre>
          <p className="setup-hint">Then restart the API server.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="portfolio-view">
        <div className="hedge-error">{error}</div>
      </div>
    );
  }

  const accentColor = isPositive ? "var(--green)" : "var(--red)";
  const gradientId = isPositive ? "areaGradientGreen" : "areaGradientRed";

  return (
    <div className="portfolio-view">
      {/* Header: total value + change */}
      <div className="portfolio-header">
        <div className="portfolio-total">
          {formatDollars(displayValue)}
        </div>
        <div
          className="portfolio-change"
          style={{ color: accentColor }}
        >
          {hoverTime ? (
            <span className="portfolio-hover-time">
              {formatTooltipTime(hoverTime)}
            </span>
          ) : (
            <>
              <span>{formatCompact(change)}</span>
              <span className="portfolio-change-pct">
                ({changePct >= 0 ? "+" : ""}
                {changePct.toFixed(2)}%)
              </span>
              <span className="portfolio-change-range">{range}</span>
            </>
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="portfolio-chart">
        {chartData.length >= 2 ? (
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart
              data={chartData}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
              margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            >
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={accentColor}
                    stopOpacity={0.25}
                  />
                  <stop
                    offset="100%"
                    stopColor={accentColor}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                minTickGap={40}
              />
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Tooltip
                content={() => null}
                cursor={{
                  stroke: "var(--text-muted)",
                  strokeWidth: 1,
                  strokeDasharray: "4 4",
                }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={accentColor}
                strokeWidth={2}
                fill={`url(#${gradientId})`}
                dot={false}
                activeDot={{
                  r: 5,
                  fill: accentColor,
                  stroke: "var(--bg-1)",
                  strokeWidth: 2,
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="portfolio-chart-empty">
            <p>No trade history found yet.</p>
            <p className="portfolio-chart-empty-sub">
              Make some trades on Kalshi and they'll show up here.
            </p>
          </div>
        )}
      </div>

      {/* Time range selector */}
      <div className="portfolio-ranges">
        {TIME_RANGES.map((r) => (
          <button
            key={r}
            className={`range-btn ${r === range ? "active" : ""}`}
            style={
              r === range ? { color: accentColor, borderBottomColor: accentColor } : undefined
            }
            onClick={() => setRange(r)}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Stats row */}
      {data && (
        <div className="portfolio-stats">
          <div className="portfolio-stat-card">
            <span className="portfolio-stat-label">Cash Balance</span>
            <span className="portfolio-stat-value">
              {formatDollars(data.balance.balance)}
            </span>
          </div>
          <div className="portfolio-stat-card">
            <span className="portfolio-stat-label">Invested</span>
            <span className="portfolio-stat-value">
              {formatDollars(data.balance.portfolio_value)}
            </span>
          </div>
          <div className="portfolio-stat-card">
            <span className="portfolio-stat-label">Open Positions</span>
            <span className="portfolio-stat-value">
              {data.positions.length}
            </span>
          </div>
          <div className="portfolio-stat-card">
            <span className="portfolio-stat-label">Total Trades</span>
            <span className="portfolio-stat-value">{history.length}</span>
          </div>
        </div>
      )}

      {/* Positions */}
      {data && data.positions.length > 0 && (
        <PositionsTable positions={data.positions} />
      )}
    </div>
  );
}

function PositionsTable({ positions }: { positions: MarketPosition[] }) {
  const sorted = useMemo(
    () =>
      [...positions].sort(
        (a, b) => Math.abs(b.market_exposure) - Math.abs(a.market_exposure)
      ),
    [positions]
  );

  return (
    <div className="portfolio-positions">
      <h3 className="portfolio-section-title">Open Positions</h3>
      <div className="table-wrapper">
        <table className="positions-table">
          <thead>
            <tr>
              <th className="col-left">Ticker</th>
              <th className="col-right">Contracts</th>
              <th className="col-right">Exposure</th>
              <th className="col-right">Realized P&L</th>
              <th className="col-right">Fees</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr key={p.ticker}>
                <td className="col-left mono">{p.ticker}</td>
                <td className="col-right">
                  <span
                    className={p.position > 0 ? "val-pos" : p.position < 0 ? "val-neg" : ""}
                  >
                    {p.position > 0 ? `${p.position} YES` : `${Math.abs(p.position)} NO`}
                  </span>
                </td>
                <td className="col-right mono">
                  {formatDollars(p.market_exposure)}
                </td>
                <td
                  className={`col-right mono ${p.realized_pnl > 0 ? "val-pos" : p.realized_pnl < 0 ? "val-neg" : ""}`}
                >
                  {formatCompact(p.realized_pnl)}
                </td>
                <td className="col-right mono" style={{ color: "var(--text-muted)" }}>
                  {formatDollars(p.fees_paid)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
