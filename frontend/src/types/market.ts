/** Shared types for the Edge Engine frontend. */

export interface MarketRow {
  ticker: string;
  question: string;
  marketPrice: number;   // 0-100
  fairProbability: number; // 0-100
  edge: number;           // signed, percentage points
  action: "BUY YES" | "BUY NO" | "HOLD";
  confidence: number;
  volume: number;
  hasLiquidity: boolean;
  reasoning: string;
  city: string;
  date: string;
  resolutionUrl: string;
  closeTime: string;
}

export interface MarketsResponse {
  markets: MarketRow[];
  meta: {
    timestamp: string;
    count: number;
    priceSource: string;
  };
}

export type SortField = keyof Pick<
  MarketRow,
  "ticker" | "marketPrice" | "fairProbability" | "edge" | "action" | "volume"
>;

export type SortDirection = "asc" | "desc";

export interface SortConfig {
  field: SortField;
  direction: SortDirection;
}
