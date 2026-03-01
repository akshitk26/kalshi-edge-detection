export interface PortfolioSnapshot {
  ts: string;
  epoch: number;
  total_value: number;
  event?: string;
}

export interface PortfolioBalance {
  balance: number;
  portfolio_value: number;
  total_value: number;
  updated_ts: number;
}

export interface MarketPosition {
  ticker: string;
  position: number;
  market_exposure: number;
  market_exposure_dollars: string;
  realized_pnl: number;
  realized_pnl_dollars: string;
  fees_paid: number;
  total_traded: number;
}

export interface PortfolioData {
  balance: PortfolioBalance;
  positions: MarketPosition[];
  timestamp: string;
}

export interface PortfolioHistory {
  snapshots: PortfolioSnapshot[];
  count: number;
}

export type TimeRange = "1D" | "1W" | "1M" | "3M" | "ALL";
