import { useState, useMemo, useCallback, useEffect, useRef } from "react";
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
  PortfolioStats,
  TradeRecord,
  TimeRange,
} from "../types/portfolio";

const TIME_RANGES: TimeRange[] = ["1D", "1W", "1M", "3M", "ALL"];

function ScrollingValue({ value }: { value: string }) {
  const prevRef = useRef(value);
  const counterRef = useRef(0);

  const prev = prevRef.current;
  const changed = value !== prev;
  const counter = changed ? counterRef.current + 1 : counterRef.current;

  useEffect(() => {
    if (prevRef.current !== value) {
      counterRef.current += 1;
      prevRef.current = value;
    }
  }, [value]);

  const prevChars = prev.split("");
  const nextChars = value.split("");
  const maxLen = Math.max(prevChars.length, nextChars.length);
  const pPad =
    prevChars.length < maxLen
      ? Array(maxLen - prevChars.length).fill(" ").concat(prevChars)
      : prevChars;
  const nPad =
    nextChars.length < maxLen
      ? Array(maxLen - nextChars.length).fill(" ").concat(nextChars)
      : nextChars;

  return (
    <span className="scroll-value">
      {nPad.map((ch, i) => {
        const oldCh = pPad[i] ?? "";
        const digitChanged = ch !== oldCh && changed;
        const isDigit = /\d/.test(ch);
        if (!isDigit || !digitChanged) {
          return (
            <span key={i} className="scroll-char scroll-static">
              {ch}
            </span>
          );
        }
        const oldNum = parseInt(oldCh);
        const newNum = parseInt(ch);
        const dir =
          !isNaN(oldNum) && !isNaN(newNum)
            ? newNum > oldNum
              ? "up"
              : "down"
            : "up";
        return (
          <span key={i} className="scroll-char scroll-digit">
            <span
              key={counter}
              className={`scroll-digit-inner scroll-digit-${dir}`}
            >
              {ch}
            </span>
          </span>
        );
      })}
    </span>
  );
}

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

function shortTicker(ticker: string): string {
  const parts = ticker.split("-");
  if (parts.length < 3) return ticker;
  const series = parts[0].replace(/^KX/, "");
  const bucket = parts.slice(2).join("-");
  return `${series} ${bucket}`;
}

interface ChartPoint {
  ts: string;
  value: number;
  label: string;
}

export function PortfolioView() {
  const { configured, data, history, stats, loading, error } = usePortfolio();
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

  const startValue = chartData.length > 0 ? chartData[0].value : 0;

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

  const hoverChange = hoverValue !== null ? (hoverValue - startValue) * 100 : null;
  const hoverPct = hoverValue !== null && startValue > 0
    ? ((hoverValue - startValue) / startValue) * 100
    : null;
  const hoverIsPositive = hoverChange !== null ? hoverChange >= 0 : isPositive;
  const activeColor = hoverValue !== null
    ? (hoverIsPositive ? "var(--green)" : "var(--red)")
    : (isPositive ? "var(--green)" : "var(--red)");

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
          <ScrollingValue value={formatDollars(displayValue)} />
        </div>
        <div
          className="portfolio-change"
          style={{ color: activeColor }}
        >
          {hoverValue !== null && hoverChange !== null && hoverPct !== null ? (
            <>
              <span>{formatCompact(hoverChange)}</span>
              <span className="portfolio-change-pct">
                ({hoverPct >= 0 ? "+" : ""}{hoverPct.toFixed(2)}%)
              </span>
              <span className="portfolio-hover-time">
                {hoverTime ? formatTooltipTime(hoverTime) : ""}
              </span>
            </>
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

      {/* Trade Performance */}
      {stats && <TradePerformance stats={stats} />}

      {/* Positions */}
      {data && data.positions.length > 0 && (
        <PositionsTable positions={data.positions} />
      )}
    </div>
  );
}

function TradeHighlight({
  label,
  icon,
  trade,
  variant,
}: {
  label: string;
  icon: string;
  trade: TradeRecord;
  variant: "best" | "worst";
}) {
  const colorClass = variant === "best" ? "val-pos" : "val-neg";
  const pctSign = variant === "best" ? "+" : "";
  return (
    <div className={`trade-highlight-card trade-highlight-${variant}`}>
      <div className="trade-hl-left">
        <div className="trade-highlight-header">
          <span className="trade-highlight-icon" dangerouslySetInnerHTML={{ __html: icon }} />
          <span className="trade-highlight-title">{label}</span>
        </div>
        <div className="trade-highlight-row">
          <span className={`trade-highlight-pct ${colorClass}`}>
            {pctSign}{trade.pct.toFixed(1)}%
          </span>
          <span className={`trade-highlight-dollars ${colorClass}`}>
            {formatCompact(trade.pnl)}
          </span>
        </div>
        <span className="trade-highlight-ticker">
          {shortTicker(trade.ticker)}
        </span>
      </div>
      <div className="trade-hl-right">
        <div className="trade-hl-detail-row">
          <span className="trade-hl-detail-label">Contracts</span>
          <span className="trade-hl-detail-value">{trade.count}</span>
        </div>
        <div className="trade-hl-detail-row">
          <span className="trade-hl-detail-label">Bought @</span>
          <span className="trade-hl-detail-value">{trade.entry_price}¢</span>
        </div>
        <div className="trade-hl-detail-row">
          <span className="trade-hl-detail-label">
            {trade.type === "sell" ? "Sold @" : "Settled @"}
          </span>
          <span className="trade-hl-detail-value">{trade.exit_price}¢</span>
        </div>
      </div>
    </div>
  );
}

function TradePerformance({ stats }: { stats: PortfolioStats }) {
  return (
    <div className="portfolio-performance">
      {/* Best / Worst trade highlight cards */}
      <div className="portfolio-trade-highlights">
        {stats.best_trade && (
          <TradeHighlight
            label="Best Trade"
            icon="&#9650;"
            trade={stats.best_trade}
            variant="best"
          />
        )}
        {stats.worst_trade && (
          <TradeHighlight
            label="Worst Trade"
            icon="&#9660;"
            trade={stats.worst_trade}
            variant="worst"
          />
        )}
      </div>

      {/* Detailed stats grid */}
      <h3 className="portfolio-section-title">Performance</h3>
      <div className="portfolio-stats">
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Total P&L</span>
          <span className={`portfolio-stat-value ${stats.total_pnl >= 0 ? "val-pos" : "val-neg"}`}>
            {formatCompact(stats.total_pnl)}
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Win Rate</span>
          <span className="portfolio-stat-value">
            {stats.win_rate}%
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">W / L</span>
          <span className="portfolio-stat-value">
            <span className="val-pos">{stats.wins}</span>
            {" / "}
            <span className="val-neg">{stats.losses}</span>
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Avg P&L</span>
          <span className={`portfolio-stat-value ${stats.avg_pnl >= 0 ? "val-pos" : "val-neg"}`}>
            {formatCompact(stats.avg_pnl)}
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Peak Value</span>
          <span className="portfolio-stat-value">
            {formatDollars(stats.peak_value)}
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Total Fees</span>
          <span className="portfolio-stat-value" style={{ color: "var(--text-muted)" }}>
            {formatDollars(stats.total_fees)}
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Markets Traded</span>
          <span className="portfolio-stat-value">
            {stats.markets_traded}
          </span>
        </div>
        <div className="portfolio-stat-card">
          <span className="portfolio-stat-label">Biggest Win</span>
          <span className="portfolio-stat-value val-pos">
            {formatCompact(stats.biggest_win)}
          </span>
        </div>
      </div>
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
