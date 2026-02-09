"""
Kalshi Market Data Client

Fetches market data from Kalshi's API or returns mock data for development.
Kalshi markets are binary prediction markets with YES/NO outcomes.

Market probability is derived from the YES price (0-100 cents = 0.00-1.00 probability).
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.data.kalshi")


@dataclass(frozen=True)
class KalshiMarket:
    """
    Immutable representation of a Kalshi market.
    
    Attributes:
        market_id: Unique identifier (ticker)
        question: Human-readable market question
        yes_price: Price of YES contract in cents (0-100)
        market_prob: Implied probability (yes_price / 100)
        close_time: When the market closes
        category: Market category (e.g., "weather")
        fetched_at: When this data was retrieved
    """
    market_id: str
    question: str
    yes_price: int  # 0-100 cents
    market_prob: float  # 0.0-1.0
    close_time: datetime
    category: str
    fetched_at: datetime

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "KalshiMarket":
        """Construct from Kalshi API response."""
        yes_price = data.get("yes_price", data.get("last_price", 50))
        return cls(
            market_id=data["ticker"],
            question=data.get("title", data.get("subtitle", "")),
            yes_price=yes_price,
            market_prob=yes_price / 100.0,
            close_time=datetime.fromisoformat(data["close_time"].replace("Z", "+00:00")),
            category=data.get("category", "unknown"),
            fetched_at=datetime.now(timezone.utc)
        )


class KalshiClient:
    """
    Client for fetching Kalshi market data.
    
    Supports both live API and mock mode for development.
    """
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize the Kalshi client.
        
        Args:
            config: Configuration dictionary with kalshi settings.
        """
        self.config = config.get("kalshi", {})
        self.base_url = self.config.get("base_url", "https://trading-api.kalshi.com/trade-api/v2")
        self.use_mock = self.config.get("use_mock", True)
        self.api_key = self.config.get("api_key") or os.getenv("KALSHI_API_KEY")
        
        # Session for connection pooling
        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})
    
    def get_weather_markets(self) -> list[KalshiMarket]:
        """
        Fetch weather-related markets.
        
        Returns:
            List of KalshiMarket objects for weather prediction markets.
        """
        if self.use_mock:
            return self._get_mock_weather_markets()
        
        return self._fetch_markets_by_category("weather")
    
    def get_market(self, market_id: str) -> KalshiMarket | None:
        """
        Fetch a specific market by ID.
        
        Args:
            market_id: The market ticker.
        
        Returns:
            KalshiMarket if found, None otherwise.
        """
        if self.use_mock:
            # Return mock if it matches our patterns
            for market in self._get_mock_weather_markets():
                if market.market_id == market_id:
                    return market
            return None
        
        try:
            response = self._session.get(f"{self.base_url}/markets/{market_id}")
            response.raise_for_status()
            data = response.json()
            return KalshiMarket.from_api_response(data["market"])
        except requests.RequestException as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            return None
    
    def _fetch_markets_by_category(self, category: str) -> list[KalshiMarket]:
        """Fetch markets from a specific category."""
        try:
            response = self._session.get(
                f"{self.base_url}/markets",
                params={"category": category, "status": "open", "limit": 50}
            )
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for market_data in data.get("markets", []):
                try:
                    markets.append(KalshiMarket.from_api_response(market_data))
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed market data: {e}")
            
            logger.info(f"Fetched {len(markets)} markets in category '{category}'")
            return markets
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch markets for category {category}: {e}")
            return []
    
    def _get_mock_weather_markets(self) -> list[KalshiMarket]:
        """
        Generate realistic mock weather markets for development.
        
        These simulate typical Kalshi weather prediction markets.
        """
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=23, minute=59, second=59)
        
        # Mock markets with varying prices to test edge detection
        mock_data = [
            {
                "market_id": "HIGHNY-26FEB09-T55",
                "question": "Will the high temperature in NYC be above 55°F on February 9?",
                "yes_price": 62,  # Market thinks 62% chance
                "category": "weather",
                "location": "NYC",
                "threshold_temp": 55,
                "threshold_type": "high_above"
            },
            {
                "market_id": "HIGHNY-26FEB09-T50",
                "question": "Will the high temperature in NYC be above 50°F on February 9?",
                "yes_price": 78,  # Market thinks 78% chance
                "category": "weather",
                "location": "NYC",
                "threshold_temp": 50,
                "threshold_type": "high_above"
            },
            {
                "market_id": "LOWNY-26FEB09-T35",
                "question": "Will the low temperature in NYC be below 35°F on February 9?",
                "yes_price": 45,  # Market thinks 45% chance
                "category": "weather",
                "location": "NYC",
                "threshold_temp": 35,
                "threshold_type": "low_below"
            },
            {
                "market_id": "HIGHLA-26FEB09-T70",
                "question": "Will the high temperature in LA be above 70°F on February 9?",
                "yes_price": 55,
                "category": "weather",
                "location": "LA",
                "threshold_temp": 70,
                "threshold_type": "high_above"
            },
            {
                "market_id": "HIGHCHI-26FEB09-T40",
                "question": "Will the high temperature in Chicago be above 40°F on February 9?",
                "yes_price": 35,
                "category": "weather",
                "location": "Chicago",
                "threshold_temp": 40,
                "threshold_type": "high_above"
            }
        ]
        
        markets = []
        for m in mock_data:
            markets.append(KalshiMarket(
                market_id=m["market_id"],
                question=m["question"],
                yes_price=m["yes_price"],
                market_prob=m["yes_price"] / 100.0,
                close_time=tomorrow,
                category=m["category"],
                fetched_at=now
            ))
        
        logger.debug(f"Generated {len(markets)} mock weather markets")
        return markets
    
    @staticmethod
    def parse_market_params(market: KalshiMarket) -> dict[str, Any] | None:
        """
        Extract structured parameters from a weather market.
        
        Parses market_id and question to extract:
        - location: City code (NYC, LA, etc.)
        - threshold_temp: Temperature threshold in Fahrenheit
        - threshold_type: "high_above", "high_below", "low_above", "low_below"
        
        Returns None if parsing fails.
        """
        # Pattern: HIGHNY-26FEB09-T55 or LOWCHI-26FEB09-T40
        pattern = r"(HIGH|LOW)([A-Z]{2,3})-\d{2}[A-Z]{3}\d{2}-T(\d+)"
        match = re.match(pattern, market.market_id)
        
        if not match:
            logger.debug(f"Could not parse market ID: {market.market_id}")
            return None
        
        high_low = match.group(1).lower()
        city_code = match.group(2)
        threshold = int(match.group(3))
        
        # Map city codes to full names for weather API
        city_map = {
            "NY": "New York",
            "LA": "Los Angeles", 
            "CHI": "Chicago",
            "MIA": "Miami",
            "SEA": "Seattle",
            "DEN": "Denver"
        }
        
        # Determine threshold type from question context
        # Most Kalshi weather markets are "above X" for highs
        if "below" in market.question.lower():
            threshold_type = f"{high_low}_below"
        else:
            threshold_type = f"{high_low}_above"
        
        return {
            "location": city_map.get(city_code, city_code),
            "threshold_temp": threshold,
            "threshold_type": threshold_type
        }
