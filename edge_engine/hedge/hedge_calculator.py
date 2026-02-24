"""
Hedge Calculator - Portfolio math for multi-NO strategy.

Given a HedgeGroup and a budget, computes optimal allocation across
NO positions to maximize expected profit where most NOs win.
"""

from dataclasses import dataclass, field
from typing import Any

from edge_engine.hedge.market_grouper import BucketInfo, HedgeGroup
from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.hedge.hedge_calculator")


@dataclass
class BucketAllocation:
    """Allocation for one bucket in the portfolio."""
    ticker: str
    range_label: str
    no_price: int            # cents per contract
    yes_price: int           # cents per contract
    contracts: int           # number of NO contracts to buy
    cost: float              # cost of contracts in dollars (excl fees)
    fees: float              # fees in dollars
    total_outlay: float      # cost + fees = total money out
    profit_if_no_wins: float # profit in dollars if this bucket does NOT win
    loss_if_yes_wins: float  # loss in dollars if this bucket DOES win
    included: bool           # whether user selected this bucket
    viable: bool             # whether passes quality filters


@dataclass
class Scenario:
    """P&L outcome when a specific bucket wins YES."""
    winning_bucket: str
    winning_label: str
    probability: float       # market-implied probability (0-1)
    net_pnl: float           # net profit/loss in dollars
    is_profitable: bool


@dataclass
class ExitSignal:
    """Signal to exit (sell) a NO position early."""
    ticker: str
    range_label: str
    entry_no_price: int      # cents, what you paid
    current_no_price: int    # cents, what it's worth now
    unrealized_pnl: float    # dollars per contract (negative = loss)
    max_loss_if_held: float  # dollars per contract if held to resolution and YES wins
    recommendation: str      # "SELL" or "HOLD"


@dataclass
class HedgeResult:
    """Complete result of a hedge calculation."""
    group_id: str
    budget: float
    fee_per_contract: float
    allocations: list[BucketAllocation] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    total_cost: float = 0.0
    total_fees: float = 0.0
    total_outlay: float = 0.0   # cost + fees
    expected_profit: float = 0.0
    worst_case_pnl: float = 0.0
    best_case_pnl: float = 0.0
    win_probability: float = 0.0   # probability-weighted % of profitable outcomes
    total_contracts: int = 0
    fee_cost_ratio: float = 0.0    # fees / cost — high = bad economics
    quality: str = "good"          # "good", "fair", "poor"
    quality_reason: str = ""       # explanation for quality rating

    def to_dict(self) -> dict[str, Any]:
        return {
            "groupId": self.group_id,
            "budget": self.budget,
            "feePerContract": self.fee_per_contract,
            "totalCost": round(self.total_cost, 2),
            "totalFees": round(self.total_fees, 2),
            "totalOutlay": round(self.total_outlay, 2),
            "expectedProfit": round(self.expected_profit, 2),
            "worstCasePnl": round(self.worst_case_pnl, 2),
            "bestCasePnl": round(self.best_case_pnl, 2),
            "winProbability": round(self.win_probability, 1),
            "totalContracts": self.total_contracts,
            "feeCostRatio": round(self.fee_cost_ratio, 2),
            "quality": self.quality,
            "qualityReason": self.quality_reason,
            "allocations": [
                {
                    "ticker": a.ticker,
                    "rangeLabel": a.range_label,
                    "noPrice": a.no_price,
                    "yesPrice": a.yes_price,
                    "contracts": a.contracts,
                    "cost": round(a.cost, 2),
                    "fees": round(a.fees, 2),
                    "totalOutlay": round(a.total_outlay, 2),
                    "profitIfNoWins": round(a.profit_if_no_wins, 2),
                    "lossIfYesWins": round(a.loss_if_yes_wins, 2),
                    "included": a.included,
                    "viable": a.viable,
                }
                for a in self.allocations
            ],
            "scenarios": [
                {
                    "winningBucket": s.winning_bucket,
                    "winningLabel": s.winning_label,
                    "probability": round(s.probability, 4),
                    "netPnl": round(s.net_pnl, 2),
                    "isProfitable": s.is_profitable,
                }
                for s in self.scenarios
            ],
        }


class HedgeCalculator:
    """
    Calculates optimal NO portfolio allocation for a hedge group.

    Strategy: Buy NO on selected buckets. Since only 1 bucket resolves YES,
    the rest resolve NO and pay out. We size positions so that expected
    profit from winning NOs exceeds the loss from the one loser.
    """

    # ── Viability thresholds ──
    MAX_NO_PRICE = 85   # Don't buy NO above 85c (too expensive, tiny profit margin)
    MIN_NO_PRICE = 5    # Don't buy NO below 5c (sucker bet, very likely to lose)
    MAX_FEE_RATIO = 0.5 # Warn if fees exceed 50% of contract cost

    def calculate(
        self,
        group: HedgeGroup,
        budget: float,
        fee_per_contract: float = 0.011,
        selected_tickers: list[str] | None = None,
    ) -> HedgeResult:
        """
        Calculate allocation for a hedge group.

        Args:
            group: The HedgeGroup to analyze.
            budget: Total budget in dollars.
            fee_per_contract: Fee per contract in dollars (default $0.011).
            selected_tickers: Which buckets to include. None = all buckets.

        Returns:
            HedgeResult with allocations and scenario analysis.
        """
        if not group.buckets:
            return HedgeResult(group_id=group.group_id, budget=budget, fee_per_contract=fee_per_contract)

        # Determine which buckets are selected
        if selected_tickers is None:
            selected = set(b.ticker for b in group.buckets)
        else:
            selected = set(selected_tickers)

        # Calculate contracts per bucket
        allocations = self._allocate_proportional(
            group, budget, fee_per_contract, selected
        )

        # Build scenario analysis with probabilities
        scenarios = self._build_scenarios(group, allocations)

        # Compute aggregates
        included_allocs = [a for a in allocations if a.included and a.contracts > 0]
        total_cost = sum(a.cost for a in included_allocs)
        total_fees = sum(a.fees for a in included_allocs)
        total_outlay = total_cost + total_fees
        total_contracts = sum(a.contracts for a in included_allocs)

        pnls = [s.net_pnl for s in scenarios]
        worst_case = min(pnls) if pnls else 0.0
        best_case = max(pnls) if pnls else 0.0

        # Expected profit: weight each scenario by market-implied probability
        expected = sum(s.probability * s.net_pnl for s in scenarios)

        # Win probability: probability-weighted chance of profit
        win_prob = sum(s.probability for s in scenarios if s.is_profitable) * 100

        # Fee-to-cost ratio
        fee_ratio = total_fees / total_cost if total_cost > 0 else 0.0

        # Quality assessment
        quality, quality_reason = self._assess_quality(
            group, included_allocs, fee_ratio, scenarios
        )

        return HedgeResult(
            group_id=group.group_id,
            budget=budget,
            fee_per_contract=fee_per_contract,
            allocations=allocations,
            scenarios=scenarios,
            total_cost=round(total_cost, 2),
            total_fees=round(total_fees, 2),
            total_outlay=round(total_outlay, 2),
            expected_profit=round(expected, 2),
            worst_case_pnl=round(worst_case, 2),
            best_case_pnl=round(best_case, 2),
            win_probability=round(win_prob, 1),
            total_contracts=total_contracts,
            fee_cost_ratio=round(fee_ratio, 2),
            quality=quality,
            quality_reason=quality_reason,
        )

    def _assess_quality(
        self,
        group: HedgeGroup,
        included: list[BucketAllocation],
        fee_ratio: float,
        scenarios: list[Scenario],
    ) -> tuple[str, str]:
        """Assess the quality of this hedge opportunity."""
        reasons = []

        # Check if only 1 bucket is viable (no diversification)
        if len(included) <= 1:
            reasons.append("Only 1 viable bucket - no diversification benefit")

        # Check fee-to-cost ratio
        if fee_ratio > self.MAX_FEE_RATIO:
            reasons.append(f"Fees are {fee_ratio:.0%} of cost - poor economics")

        # Check if market is strongly skewed (one bucket > 90%)
        max_yes = max(b.yes_price for b in group.buckets) if group.buckets else 0
        if max_yes >= 90:
            reasons.append(f"Market is {max_yes}% resolved - nearly settled")

        # Check expected profit
        expected = sum(s.probability * s.net_pnl for s in scenarios)
        if expected < 0:
            reasons.append("Negative expected value")

        if len(reasons) >= 2 or (len(reasons) == 1 and "resolved" in reasons[0]):
            return "poor", "; ".join(reasons)
        elif len(reasons) == 1:
            return "fair", reasons[0]
        return "good", ""

    def _allocate_proportional(
        self,
        group: HedgeGroup,
        budget: float,
        fee_per_contract: float,
        selected: set[str],
    ) -> list[BucketAllocation]:
        """
        Allocate budget weighted by profit margin across viable buckets.

        Buckets with cheaper NO (higher profit margin) get proportionally
        more capital. Auto-excludes buckets where:
        - NO price > MAX_NO_PRICE (too expensive, tiny profit)
        - NO price < MIN_NO_PRICE (sucker bet)
        - Profit after fees <= 0
        """
        allocations = []
        budget_cents = budget * 100

        # First pass: find viable buckets and their profit margins
        viable: list[tuple[str, float]] = []  # (ticker, margin_weight)
        for b in group.buckets:
            if b.ticker not in selected:
                continue
            if b.no_price < self.MIN_NO_PRICE or b.no_price > self.MAX_NO_PRICE:
                continue
            profit_per_contract = (100 - b.no_price) / 100 - fee_per_contract
            if profit_per_contract <= 0:
                continue
            # Weight = profit margin ratio: how much you earn vs how much you risk
            # Cheap NOs (e.g. 50c → margin 1.0) get more than expensive NOs (80c → margin 0.25)
            margin_weight = (100 - b.no_price) / b.no_price
            viable.append((b.ticker, margin_weight))

        viable_tickers = {t for t, _ in viable}
        total_weight = sum(w for _, w in viable)

        # Build lookup for weights
        weight_map = {t: w for t, w in viable}

        for b in group.buckets:
            included = b.ticker in selected
            is_viable = b.ticker in viable_tickers

            if included and is_viable and total_weight > 0:
                # Budget share proportional to profit margin
                bucket_share = (weight_map[b.ticker] / total_weight) * budget_cents
                cost_per_contract = b.no_price + (fee_per_contract * 100)  # cents
                contracts = int(bucket_share / cost_per_contract) if cost_per_contract > 0 else 0
                contracts = max(contracts, 0)

                cost_dollars = contracts * b.no_price / 100
                fee_dollars = contracts * fee_per_contract
                total_outlay = cost_dollars + fee_dollars
                profit_if_no = contracts * (100 - b.no_price) / 100 - fee_dollars
                loss_if_yes = -(cost_dollars + fee_dollars)
            else:
                contracts = 0
                cost_dollars = 0.0
                fee_dollars = 0.0
                total_outlay = 0.0
                profit_if_no = 0.0
                loss_if_yes = 0.0

            allocations.append(BucketAllocation(
                ticker=b.ticker,
                range_label=b.range_label,
                no_price=b.no_price,
                yes_price=b.yes_price,
                contracts=contracts,
                cost=cost_dollars,
                fees=fee_dollars,
                total_outlay=total_outlay,
                profit_if_no_wins=profit_if_no,
                loss_if_yes_wins=loss_if_yes,
                included=included,
                viable=is_viable,
            ))

        return allocations

    def _build_scenarios(
        self,
        group: HedgeGroup,
        allocations: list[BucketAllocation],
    ) -> list[Scenario]:
        """
        For each bucket, compute net P&L if that bucket wins YES.

        Each scenario carries a market-implied probability:
        P(bucket i wins) = yes_price_i / sum(all_yes_prices)
        """
        scenarios = []
        included = [a for a in allocations if a.included and a.contracts > 0]
        sum_yes = group.sum_yes_prices or 1

        for j, bucket in enumerate(group.buckets):
            prob = bucket.yes_price / sum_yes

            net_pnl = 0.0
            for a in included:
                if a.ticker == bucket.ticker:
                    net_pnl += a.loss_if_yes_wins
                else:
                    net_pnl += a.profit_if_no_wins

            scenarios.append(Scenario(
                winning_bucket=bucket.ticker,
                winning_label=bucket.range_label,
                probability=prob,
                net_pnl=round(net_pnl, 2),
                is_profitable=net_pnl > 0,
            ))

        return scenarios

    @staticmethod
    def evaluate_exit(
        entry_no_price: int,
        current_no_price: int,
        exit_threshold: float = 0.30,
    ) -> ExitSignal:
        """
        Evaluate whether to exit a NO position early.

        Args:
            entry_no_price: What you paid for NO (cents).
            current_no_price: Current NO price (cents, what you could sell for).
            exit_threshold: If unrealized loss exceeds this fraction of entry, recommend sell.

        Returns:
            ExitSignal with recommendation.
        """
        unrealized_cents = current_no_price - entry_no_price
        unrealized_dollars = unrealized_cents / 100
        max_loss = -entry_no_price / 100

        loss_fraction = abs(unrealized_cents) / entry_no_price if entry_no_price > 0 else 0
        recommend = "SELL" if (unrealized_cents < 0 and loss_fraction >= exit_threshold) else "HOLD"

        return ExitSignal(
            ticker="",
            range_label="",
            entry_no_price=entry_no_price,
            current_no_price=current_no_price,
            unrealized_pnl=unrealized_dollars,
            max_loss_if_held=max_loss,
            recommendation=recommend,
        )
