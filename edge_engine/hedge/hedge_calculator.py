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
    no_price: int  # cents per contract
    yes_price: int  # cents per contract
    contracts: int  # number of NO contracts to buy
    cost: float  # cost of contracts in dollars (excl fees)
    fees: float  # fees in dollars
    total_outlay: float  # cost + fees = total money out
    profit_if_no_wins: float  # profit in dollars if this bucket does NOT win
    loss_if_yes_wins: float  # loss in dollars if this bucket DOES win
    included: bool  # whether user selected this bucket
    viable: bool  # whether passes quality filters


@dataclass
class Scenario:
    """P&L outcome when a specific bucket wins YES."""

    winning_bucket: str
    winning_label: str
    probability: float  # market-implied probability (0-1)
    net_pnl: float  # net profit/loss in dollars
    is_profitable: bool


@dataclass
class ExitSignal:
    """Signal to exit (sell) a NO position early."""

    ticker: str
    range_label: str
    entry_no_price: int  # cents, what you paid
    current_no_price: int  # cents, what it's worth now
    unrealized_pnl: float  # dollars per contract (negative = loss)
    max_loss_if_held: float  # dollars per contract if held to resolution and YES wins
    recommendation: str  # "SELL" or "HOLD"


@dataclass
class ExitAnalysis:
    """Analysis of dynamic exit for a single bucket."""

    ticker: str
    range_label: str
    entry_no_price: int  # cents
    exit_no_price: int  # price at which we'd exit (cents)
    contracts: int  # number of contracts
    exit_trigger_yes_prob: float  # threshold % where we'd exit
    num_other_buckets: int  # how many other buckets we're holding
    profit_per_other_bucket: float  # profit from each other bucket when they resolve to NO
    profit_from_others: float  # total profit from other buckets
    entry_cost: float  # total cost for this bucket
    loss_if_held: float  # loss if this bucket resolves YES (full loss)
    loss_if_exit: float  # loss if we exit at threshold
    net_pnl: float  # profit_from_others + loss_if_exit
    improvement: float  # loss_if_held - loss_if_exit (saved by exiting early)


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
    total_outlay: float = 0.0  # cost + fees
    expected_profit: float = 0.0
    adjusted_expected_profit: float = 0.0  # EV with dynamic exit
    worst_case_pnl: float = 0.0
    best_case_pnl: float = 0.0
    win_probability: float = 0.0  # probability-weighted % of profitable outcomes
    total_contracts: int = 0
    fee_cost_ratio: float = 0.0  # fees / cost — high = bad economics
    quality: str = "good"  # "good", "fair", "poor"
    quality_reason: str = ""  # explanation for quality rating
    exit_threshold: float = 0.65  # YES probability threshold for exit
    exit_analysis: list[ExitAnalysis] = field(default_factory=list)

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
            "adjustedExpectedProfit": round(self.adjusted_expected_profit, 2),
            "exitThreshold": self.exit_threshold,
            "exitAnalysis": [
                {
                    "ticker": e.ticker,
                    "rangeLabel": e.range_label,
                    "entryNoPrice": e.entry_no_price,
                    "exitNoPrice": e.exit_no_price,
                    "contracts": e.contracts,
                    "exitTriggerYesProb": round(e.exit_trigger_yes_prob, 4),
                    "numOtherBuckets": e.num_other_buckets,
                    "profitPerOtherBucket": round(e.profit_per_other_bucket, 2),
                    "profitFromOthers": round(e.profit_from_others, 2),
                    "entryCost": round(e.entry_cost, 2),
                    "lossIfHeld": round(e.loss_if_held, 2),
                    "lossIfExit": round(e.loss_if_exit, 2),
                    "netPnl": round(e.net_pnl, 2),
                    "improvement": round(e.improvement, 2),
                }
                for e in self.exit_analysis
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
    MAX_NO_PRICE = 87  # Don't buy NO above 87c (too expensive, tiny profit margin)
    MIN_NO_PRICE = 5  # Don't buy NO below 5c (sucker bet, very likely to lose)
    MAX_FEE_RATIO = 0.5  # Warn if fees exceed 50% of contract cost

    def calculate(
        self,
        group: HedgeGroup,
        budget: float,
        fee_per_contract: float = 0.011,
        selected_tickers: list[str] | None = None,
        config: dict | None = None,
    ) -> HedgeResult:
        """
        Calculate allocation for a hedge group.

        Args:
            group: The HedgeGroup to analyze.
            budget: Total budget in dollars.
            fee_per_contract: Fee per contract in dollars (default $0.011).
            selected_tickers: Which buckets to include. None = all buckets.
            config: Optional config dict with hedge settings.

        Returns:
            HedgeResult with allocations and scenario analysis.
        """
        config = config or {}
        exit_threshold = config.get("hedge", {}).get("exit_threshold", 0.65)
        enable_dynamic_exit = config.get("hedge", {}).get("enable_dynamic_exit", True)

        if not group.buckets:
            return HedgeResult(
                group_id=group.group_id,
                budget=budget,
                fee_per_contract=fee_per_contract,
                exit_threshold=exit_threshold,
            )

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

        # Dynamic exit calculation
        adjusted_expected = expected
        exit_analysis: list[ExitAnalysis] = []

        if enable_dynamic_exit and included_allocs:
            adjusted_expected, exit_analysis = self._calculate_dynamic_exit(
                group, allocations, scenarios, fee_per_contract, exit_threshold
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
            adjusted_expected_profit=round(adjusted_expected, 2),
            worst_case_pnl=round(worst_case, 2),
            best_case_pnl=round(best_case, 2),
            win_probability=round(win_prob, 1),
            total_contracts=total_contracts,
            fee_cost_ratio=round(fee_ratio, 2),
            quality=quality,
            quality_reason=quality_reason,
            exit_threshold=exit_threshold,
            exit_analysis=exit_analysis,
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
                contracts = (
                    int(bucket_share / cost_per_contract)
                    if cost_per_contract > 0
                    else 0
                )
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

            allocations.append(
                BucketAllocation(
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
                )
            )

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

            scenarios.append(
                Scenario(
                    winning_bucket=bucket.ticker,
                    winning_label=bucket.range_label,
                    probability=prob,
                    net_pnl=round(net_pnl, 2),
                    is_profitable=net_pnl > 0,
                )
            )

        return scenarios

    def _calculate_dynamic_exit(
        self,
        group: HedgeGroup,
        allocations: list[BucketAllocation],
        scenarios: list[Scenario],
        fee_per_contract: float,
        exit_threshold: float,
    ) -> tuple[float, list[ExitAnalysis]]:
        """
        Calculate adjusted EV with dynamic exit strategy.

        Logic:
        - We hold NO on multiple buckets
        - If any bucket's YES probability rises to exit_threshold or higher, we exit that position early
        - At exit point: YES = exit_threshold, so NO = (1 - exit_threshold) * 100 cents
        - Exit loss = (entry NO price - exit NO price) / 100 * contracts
        - vs. holding to resolution: full loss = entry NO price / 100 * contracts

        The improvement comes from capping our loss at the exit price rather than
        holding to full resolution when the bucket ends up winning YES.

        Args:
            group: The hedge group
            allocations: Current allocations
            scenarios: Static scenarios
            fee_per_contract: Fee per contract
            exit_threshold: Exit when YES prob exceeds this

        Returns:
            Tuple of (adjusted_expected_profit, exit_analysis)
        """
        included_allocs = [a for a in allocations if a.included and a.contracts > 0]
        if not included_allocs:
            return 0.0, []

        exit_analysis: list[ExitAnalysis] = []

        # Build lookup: ticker -> allocation
        alloc_by_ticker = {a.ticker: a for a in included_allocs}

        # Calculate static EV for comparison
        static_ev = sum(s.probability * s.net_pnl for s in scenarios)

        # Exit NO price at threshold: if YES = exit_threshold, then NO = 100 - exit_threshold (in cents)
        exit_no_price = int((1 - exit_threshold) * 100)

        # Calculate adjusted EV
        # For each scenario (bucket winning YES), we now assume we exit at threshold
        # instead of holding to resolution
        adjusted_scenario_ev = 0.0

        for scenario in scenarios:
            winning_bucket = scenario.winning_bucket

            # Find the allocation for the winning bucket
            winning_alloc = alloc_by_ticker.get(winning_bucket)

            if winning_alloc is None:
                # This bucket wasn't included, use static EV
                adjusted_scenario_ev += scenario.probability * scenario.net_pnl
                continue

            # Calculate exit loss at threshold
            # We bought NO at winning_alloc.no_price cents
            # If we exit when YES reaches exit_threshold, NO is at exit_no_price cents
            # Loss per contract = (entry - exit) / 100
            cents_lost_per_contract = max(0, winning_alloc.no_price - exit_no_price)
            exit_loss_dollars = -winning_alloc.contracts * (
                cents_lost_per_contract / 100
            )

            # Recalculate PnL with early exit
            # - The winning bucket: we exit at threshold (partial loss)
            # - Other buckets: we hold to resolution (full profit)
            adjusted_pnl = 0.0
            for a in included_allocs:
                if a.ticker == winning_bucket:
                    # Partial loss from early exit instead of full loss
                    adjusted_pnl += exit_loss_dollars
                else:
                    # This bucket resolves NO, we profit (held to resolution)
                    adjusted_pnl += a.profit_if_no_wins

            adjusted_scenario_ev += scenario.probability * adjusted_pnl

        # Build exit analysis for each bucket
        # For each bucket, calculate what happens if THAT bucket exits at threshold
        # and all OTHER buckets resolve to NO
        for alloc in included_allocs:
            # Entry cost for this bucket
            entry_cost = alloc.contracts * alloc.no_price / 100
            
            # Loss if held to resolution (full loss = we lose what we paid)
            loss_if_held = -entry_cost
            
            # Loss if we exit at threshold
            cents_lost_per_contract = max(0, alloc.no_price - exit_no_price)
            loss_if_exit = -alloc.contracts * (cents_lost_per_contract / 100)
            
            # Calculate profit from other buckets (they resolve to NO)
            # Each other bucket gives us: contracts * (100 - no_price) / 100 profit
            profit_per_other = 0.0
            for other_alloc in included_allocs:
                if other_alloc.ticker != alloc.ticker:
                    profit_per_other += other_alloc.contracts * (100 - other_alloc.no_price) / 100
            
            num_others = len(included_allocs) - 1
            
            # Average profit per other bucket (for display)
            avg_profit_per_other = profit_per_other / num_others if num_others > 0 else 0
            
            # Net P&L: profit from others + loss from this bucket exiting
            net_pnl = profit_per_other + loss_if_exit
            
            # Improvement: how much we save by exiting early vs holding
            improvement = abs(loss_if_held) - abs(loss_if_exit)
            
            exit_analysis.append(
                ExitAnalysis(
                    ticker=alloc.ticker,
                    range_label=alloc.range_label,
                    entry_no_price=alloc.no_price,
                    exit_no_price=exit_no_price,
                    contracts=alloc.contracts,
                    exit_trigger_yes_prob=exit_threshold,
                    num_other_buckets=num_others,
                    profit_per_other_bucket=round(avg_profit_per_other, 2),
                    profit_from_others=round(profit_per_other, 2),
                    entry_cost=round(entry_cost, 2),
                    loss_if_held=round(loss_if_held, 2),
                    loss_if_exit=round(loss_if_exit, 2),
                    net_pnl=round(net_pnl, 2),
                    improvement=round(improvement, 2),
                )
            )

        return adjusted_scenario_ev, exit_analysis

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

        loss_fraction = (
            abs(unrealized_cents) / entry_no_price if entry_no_price > 0 else 0
        )
        recommend = (
            "SELL"
            if (unrealized_cents < 0 and loss_fraction >= exit_threshold)
            else "HOLD"
        )

        return ExitSignal(
            ticker="",
            range_label="",
            entry_no_price=entry_no_price,
            current_no_price=current_no_price,
            unrealized_pnl=unrealized_dollars,
            max_loss_if_held=max_loss,
            recommendation=recommend,
        )
