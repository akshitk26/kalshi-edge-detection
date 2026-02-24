"""
Market Grouper - Groups Kalshi markets into hedge-able groups.

Takes individual bucket/threshold markets and groups them by (city, date, high/low)
so the hedge calculator can analyze them as a portfolio.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from edge_engine.data.kalshi_client import KalshiMarket, KalshiClient
from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.hedge.market_grouper")


@dataclass
class BucketInfo:
    """One bucket within a hedge group."""
    ticker: str
    range_label: str         # e.g., "30° to 31°", "≤27°", "≥36°"
    yes_price: int           # cents (what you'd pay for YES)
    no_price: int            # cents (what you'd pay for NO = NO ask)
    yes_bid: int
    yes_ask: int
    no_bid: int
    no_ask: int
    has_liquidity: bool
    volume: int
    question: str
    close_time: datetime
    kalshi_url: str

    @property
    def no_profit_if_wins(self) -> int:
        """Profit per contract if this NO resolves (in cents)."""
        return 100 - self.no_price

    @property
    def no_loss_if_loses(self) -> int:
        """Loss per contract if this YES resolves (in cents)."""
        return self.no_price


@dataclass
class HedgeGroup:
    """A group of mutually exclusive buckets for one city-date."""
    group_id: str            # e.g., "KXHIGHNY-26FEB24"
    city: str
    date: str                # e.g., "26FEB24"
    market_type: str         # "high" or "low"
    buckets: list[BucketInfo] = field(default_factory=list)

    @property
    def num_buckets(self) -> int:
        return len(self.buckets)

    @property
    def sum_yes_prices(self) -> int:
        """Sum of all YES prices in cents. >100 means overround exists."""
        return sum(b.yes_price for b in self.buckets)

    @property
    def overround(self) -> float:
        """Overround as percentage points (e.g., 9.0 means 109% total)."""
        return self.sum_yes_prices - 100

    @property
    def sum_no_prices(self) -> int:
        """Total cost to buy NO on every bucket (in cents per contract)."""
        return sum(b.no_price for b in self.buckets)

    @property
    def all_have_liquidity(self) -> bool:
        return all(b.has_liquidity for b in self.buckets)

    @property
    def kalshi_url(self) -> str:
        series = self.group_id.split("-")[0].lower()
        return f"https://kalshi.com/markets/{series}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "groupId": self.group_id,
            "city": self.city,
            "date": self.date,
            "marketType": self.market_type,
            "numBuckets": self.num_buckets,
            "sumYesPrices": self.sum_yes_prices,
            "overround": round(self.overround, 1),
            "sumNoPrices": self.sum_no_prices,
            "allHaveLiquidity": self.all_have_liquidity,
            "kalshiUrl": self.kalshi_url,
            "buckets": [
                {
                    "ticker": b.ticker,
                    "rangeLabel": b.range_label,
                    "yesPrice": b.yes_price,
                    "noPrice": b.no_price,
                    "yesBid": b.yes_bid,
                    "yesAsk": b.yes_ask,
                    "noBid": b.no_bid,
                    "noAsk": b.no_ask,
                    "hasLiquidity": b.has_liquidity,
                    "volume": b.volume,
                    "question": b.question,
                    "closeTime": b.close_time.isoformat(),
                    "kalshiUrl": b.kalshi_url,
                    "noProfitIfWins": b.no_profit_if_wins,
                    "noLossIfLoses": b.no_loss_if_loses,
                }
                for b in self.buckets
            ],
        }


class MarketGrouper:
    """Groups individual Kalshi markets into hedge groups by city+date."""

    # City code mapping (reuses KalshiClient's logic)
    CITY_MAP = {
        "NY": "New York", "CHI": "Chicago", "LAX": "Los Angeles",
        "LA": "Los Angeles", "MIA": "Miami", "BOS": "Boston",
        "DEN": "Denver", "ATL": "Atlanta", "PHL": "Philadelphia",
        "PHX": "Phoenix", "TATL": "Atlanta", "TBOS": "Boston",
    }

    # Pattern: KXHIGH<CITY>-<DATE>-<BUCKET_OR_THRESHOLD>
    TICKER_PATTERN = re.compile(
        r"KX(HIGH|LOW)([A-Z]{2,5})-(\d{2}[A-Z]{3}\d{2})-([BT])([\d.]+)"
    )

    def group_markets(self, markets: list[KalshiMarket]) -> list[HedgeGroup]:
        """
        Group markets into HedgeGroups.

        Args:
            markets: List of KalshiMarket objects (from client).

        Returns:
            List of HedgeGroup objects, sorted by date then city.
        """
        groups: dict[str, HedgeGroup] = {}

        for market in markets:
            match = self.TICKER_PATTERN.match(market.market_id)
            if not match:
                logger.debug(f"Skipping non-matching ticker: {market.market_id}")
                continue

            high_low = match.group(1).lower()   # "high" or "low"
            city_code = match.group(2)
            date_str = match.group(3)           # e.g., "26FEB24"
            bucket_or_thresh = match.group(4)   # "B" or "T"
            value = match.group(5)              # e.g., "46.5" or "40"

            city = self.CITY_MAP.get(city_code, city_code)
            series = f"KX{match.group(1)}{city_code}"
            group_id = f"{series}-{date_str}"

            if group_id not in groups:
                groups[group_id] = HedgeGroup(
                    group_id=group_id,
                    city=city,
                    date=date_str,
                    market_type=high_low,
                )

            # Build range label from question or ticker
            range_label = self._extract_range_label(market, bucket_or_thresh, value)

            # Determine NO price: use no_ask (cost to buy NO), fallback to 100 - yes_price
            no_price = market.no_ask if market.no_ask > 0 else (100 - market.yes_price)

            bucket = BucketInfo(
                ticker=market.market_id,
                range_label=range_label,
                yes_price=market.yes_price,
                no_price=no_price,
                yes_bid=market.yes_bid,
                yes_ask=market.yes_ask,
                no_bid=market.no_bid,
                no_ask=market.no_ask,
                has_liquidity=market.has_liquidity,
                volume=market.volume,
                question=market.question,
                close_time=market.close_time,
                kalshi_url=f"https://kalshi.com/markets/{series.lower()}",
            )

            groups[group_id].buckets.append(bucket)

        # Sort buckets within each group by threshold value ascending (matches Kalshi order)
        for group in groups.values():
            group.buckets.sort(key=lambda b: self._bucket_sort_key(b.range_label))

        # Sort groups by date, then city
        result = sorted(groups.values(), key=lambda g: (g.date, g.city))

        logger.info(f"Grouped {len(markets)} markets into {len(result)} hedge groups")
        return result

    @staticmethod
    def _extract_range_label(market: KalshiMarket, bucket_type: str, value: str) -> str:
        """Extract a human-readable range label from the question or ticker."""
        q = market.question.lower()

        # Try to extract from subtitle/question first
        # Common patterns: "28° to 29°", "27° or below", "36° or above"
        range_match = re.search(r"(\d+°?\s*(to|or\s+below|or\s+above|and\s+above)\s*\d*°?)", q)
        if range_match:
            return range_match.group(1).strip()

        # Fallback: build from ticker
        val = float(value)
        if bucket_type == "B":
            lower = int(val)
            return f"{lower}° to {lower + 1}°"
        else:
            # Threshold
            if "below" in q or "<" in q:
                return f"≤{int(val)}°"
            elif "above" in q or ">" in q:
                return f"≥{int(val)}°"
            return f"{int(val)}°"

    @staticmethod
    def _bucket_sort_key(range_label: str) -> float:
        """Extract a numeric sort key from a range label for ascending order.
        
        'or below' → sort first, 'or above' → sort last, otherwise use first number.
        """
        label = range_label.lower()
        nums = re.findall(r"[\d.]+", label)
        if not nums:
            return 0.0
        first_num = float(nums[0])
        if "below" in label:
            return first_num - 1000   # sort first
        if "above" in label:
            return first_num + 1000   # sort last
        return first_num
