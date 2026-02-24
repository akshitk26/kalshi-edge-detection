/** Types for the hedge dashboard. */

export interface BucketInfo {
  ticker: string;
  rangeLabel: string;
  yesPrice: number;
  noPrice: number;
  yesBid: number;
  yesAsk: number;
  noBid: number;
  noAsk: number;
  hasLiquidity: boolean;
  volume: number;
  question: string;
  closeTime: string;
  kalshiUrl: string;
  noProfitIfWins: number;
  noLossIfLoses: number;
}

export interface HedgeGroup {
  groupId: string;
  city: string;
  date: string;
  marketType: string;
  numBuckets: number;
  sumYesPrices: number;
  overround: number;
  sumNoPrices: number;
  allHaveLiquidity: boolean;
  kalshiUrl: string;
  buckets: BucketInfo[];
}

export interface BucketAllocation {
  ticker: string;
  rangeLabel: string;
  noPrice: number;
  yesPrice: number;
  contracts: number;
  cost: number;
  fees: number;
  totalOutlay: number;
  profitIfNoWins: number;
  lossIfYesWins: number;
  included: boolean;
  viable: boolean;
}

export interface Scenario {
  winningBucket: string;
  winningLabel: string;
  probability: number;
  netPnl: number;
  isProfitable: boolean;
}

export interface HedgeResult {
  groupId: string;
  budget: number;
  feePerContract: number;
  totalCost: number;
  totalFees: number;
  totalOutlay: number;
  expectedProfit: number;
  worstCasePnl: number;
  bestCasePnl: number;
  winProbability: number;
  totalContracts: number;
  feeCostRatio: number;
  quality: "good" | "fair" | "poor";
  qualityReason: string;
  allocations: BucketAllocation[];
  scenarios: Scenario[];
}

export interface HedgeGroupsResponse {
  groups: HedgeGroup[];
  meta: {
    timestamp: string;
    count: number;
    totalMarkets: number;
    priceSource: string;
  };
}

export interface HedgeCalculateResponse {
  allocation: HedgeResult;
  group: HedgeGroup;
}
