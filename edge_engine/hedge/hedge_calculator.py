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
    cost: float              # total cost in dollars
    profit_if_no_wins: float # profit in dollars if this bucket does NOT win
    loss_if_yes_wins: float  # loss in dollars if this bucket DOES win
    included: bool           # whether user selected this bucket


@dataclass
class Scenario:
    """P&L outcome when a specific bucket wins YES."""
    winning_bucket: str
    winning_label: str
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
    expected_profit: float = 0.0
    worst_case_pnl: float = 0.0
    best_case_pnl: float = 0.0
    win_probability: float = 0.0   # % of scenarios that are profitable
    total_contracts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "groupId": self.group_id,
            "budget": self.budget,
            "feePerContract": self.fee_per_contract,
            "totalCost": round(self.total_cost, 2),
            "totalFees": round(self.total_fees, 2),
            "expectedProfit": round(self.expected_profit, 2),
            "worstCasePnl": round(self.worst_case_pnl, 2),
            "bestCasePnl": round(self.best_case_pnl, 2),
            "winProbability": round(self.win_probability, 1),
            "totalContracts": self.total_contracts,
            "allocations": [
                {
                    "ticker": a.ticker,
                    "rangeLabel": a.range_label,
                    "noPrice": a.no_price,
                    "yesPrice": a.yes_price,
                    "contracts": a.contracts,
                    "cost": round(a.cost, 2),
                    "profitIfNoWins": round(a.profit_if_no_wins, 2),
                    "lossIfYesWins": round(a.loss_if_yes_wins, 2),
                    "included": a.included,
                }
                for a in self.allocations
            ],
            "scenarios": [
                {
                    "winningBucket": s.winning_bucket,
                    "winningLabel": s.winning_label,
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

        # Calculate contracts per bucket using proportional allocation
        # Strategy: allocate more contracts to buckets with cheaper NO (higher YES)
        # because those have the best profit/risk ratio when NO wins
        allocations = self._allocate_proportional(
            group, budget, fee_per_contract, selected
        )

        # Build scenario analysis: for each bucket, what happens if it wins YES?
        scenarios = self._build_scenarios(group, allocations)

        # Compute aggregates
        total_cost = sum(a.cost for a in allocations if a.included)
        total_contracts = sum(a.contracts for a in allocations if a.included)
        total_fees = total_contracts * fee_per_contract

        pnls = [s.net_pnl for s in scenarios]
        worst_case = min(pnls) if pnls else 0.0
        best_case = max(pnls) if pnls else 0.0

        # Expected profit: weight each scenario by market-implied probability
        # P(bucket i wins) ≈ yes_price_i / sum_yes_prices
        sum_yes = group.sum_yes_prices or 1
        expected = 0.0
        profitable_scenarios = 0
        for i, bucket in enumerate(group.buckets):
            prob = bucket.yes_price / sum_yes
            if i < len(scenarios):
                expected += prob * scenarios[i].net_pnl
                if scenarios[i].is_profitable:
                    profitable_scenarios += 1

        win_prob = (profitable_scenarios / len(scenarios) * 100) if scenarios else 0

        return HedgeResult(
            group_id=group.group_id,
            budget=budget,
            fee_per_contract=fee_per_contract,
            allocations=allocations,
            scenarios=scenarios,
            total_cost=round(total_cost, 2),
            total_fees=round(total_fees, 2),
            expected_profit=round(expected, 2),
            worst_case_pnl=round(worst_case, 2),
            best_case_pnl=round(best_case, 2),
            win_probability=round(win_prob, 1),
            total_contracts=total_contracts,
        )

    def _allocate_proportional(
        self,
        group: HedgeGroup,
        budget: float,
        fee_per_contract: float,
        selected: set[str],
    ) -> list[BucketAllocation]:
        """
        Allocate budget proportionally across selected buckets.

        Weight by profit-to-cost ratio: buckets with cheaper NO (= higher YES price)
        get more contracts because each NO win yields more profit.
        """
        allocations = []
        budget_cents = budget * 100

        # Calculate weights for selected buckets
        # Weight = (profit if NO wins) / (cost of NO) = (100 - no_price) / no_price
        # Higher weight = better risk/reward
        weights: dict[str, float] = {}
        for b in group.buckets:
            if b.ticker in selected and b.no_price > 0:
                profit_ratio = (100 - b.no_price) / b.no_price
                weights[b.ticker] = max(profit_ratio, 0.01)  # floor to avoid 0

        total_weight = sum(weights.values()) or 1

        for b in group.buckets:
            included = b.ticker in selected

            if included and b.ticker in weights:
                # Proportional share of budget
                share = weights[b.ticker] / total_weight
                budget_for_bucket = budget_cents * share

                # How many contracts can we buy?
                cost_per_contract = b.no_price + (fee_per_contract * 100)  # cents
                contracts = int(budget_for_bucket / cost_per_contract) if cost_per_contract > 0 else 0
                contracts = max(contracts, 0)

                cost_dollars = contracts * b.no_price / 100
                fee_dollars = contracts * fee_per_contract
                profit_if_no = contracts * (100 - b.no_price) / 100 - fee_dollars
                loss_if_yes = -(cost_dollars + fee_dollars)
            else:
                contracts = 0
                cost_dollars = 0
                profit_if_no = 0
                loss_if_yes = 0

            allocations.append(BucketAllocation(
                ticker=b.ticker,
                range_label=b.range_label,
                no_price=b.no_price,
                yes_price=b.yes_price,
                contracts=contracts,
                cost=cost_dollars,
                profit_if_no_wins=profit_if_no,
                loss_if_yes_wins=loss_if_yes,
                included=included,
            ))

        return allocations

    def _build_scenarios(
        self,
        group: HedgeGroup,
        allocations: list[BucketAllocation],
    ) -> list[Scenario]:
        """
        For each bucket, compute net P&L if that bucket wins YES.

        When bucket j wins:
          - All other included NOs pay out (profit)
          - NO on bucket j loses (loss)
        """
        scenarios = []
        included = [a for a in allocations if a.included and a.contracts > 0]

        for j, bucket in enumerate(group.buckets):
            # Find the allocation for this bucket
            alloc_j = next((a for a in allocations if a.ticker == bucket.ticker), None)

            net_pnl = 0.0
            for a in included:
                if a.ticker == bucket.ticker:
                    # This NO loses — we lose our cost
                    net_pnl += a.loss_if_yes_wins
                else:
                    # This NO wins — we get profit
                    net_pnl += a.profit_if_no_wins

            scenarios.append(Scenario(
                winning_bucket=bucket.ticker,
                winning_label=bucket.range_label,
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
        # Unrealized P&L per contract (negative = loss)
        unrealized_cents = current_no_price - entry_no_price
        unrealized_dollars = unrealized_cents / 100

        # Max loss if held to resolution and YES wins
        max_loss = -entry_no_price / 100

        # Threshold check: if we've lost >X% of our entry price, recommend selling
        loss_fraction = abs(unrealized_cents) / entry_no_price if entry_no_price > 0 else 0
        recommend = "SELL" if (unrealized_cents < 0 and loss_fraction >= exit_threshold) else "HOLD"

        return ExitSignal(
            ticker="",  # filled in by caller
            range_label="",
            entry_no_price=entry_no_price,
            current_no_price=current_no_price,
            unrealized_pnl=unrealized_dollars,
            max_loss_if_held=max_loss,
            recommendation=recommend,
        )
