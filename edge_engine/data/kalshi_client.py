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
        volume: Trading volume
        has_liquidity: Whether market has active bid/ask
    """
    market_id: str
    question: str
    yes_price: int  # 0-100 cents
    market_prob: float  # 0.0-1.0
    close_time: datetime
    category: str
    fetched_at: datetime
    volume: int = 0
    has_liquidity: bool = True

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "KalshiMarket":
        """Construct from Kalshi API response."""
        yes_bid = data.get("yes_bid", 0) or 0
        yes_ask = data.get("yes_ask", 0) or 0
        last_price = data.get("last_price", 0) or 0
        
        # Kalshi website shows "Chance" as last_price (the last traded price)
        # This is the most accurate representation of market consensus
        # has_liquidity indicates if there are active buyers/sellers
        has_liquidity = yes_bid > 0 and yes_ask > 0 and (yes_ask - yes_bid) <= 15
        
        # Use last_price as primary (matches Kalshi website "Chance")
        # Fall back to midpoint if no trades yet
        if last_price > 0:
            yes_price = last_price
        elif has_liquidity:
            yes_price = (yes_bid + yes_ask) // 2
        elif yes_ask > 0:
            yes_price = yes_ask
        elif yes_bid > 0:
            yes_price = yes_bid
        else:
            yes_price = 50  # Unknown, assume 50%
        
        # Build question from title + subtitle
        title = data.get("title", "")
        subtitle = data.get("subtitle", "")
        question = f"{title}: {subtitle}" if subtitle else title
        
        return cls(
            market_id=data["ticker"],
            question=question,
            yes_price=yes_price,
            market_prob=yes_price / 100.0,
            close_time=datetime.fromisoformat(data["close_time"].replace("Z", "+00:00")),
            category=data.get("category", "unknown"),
            fetched_at=datetime.now(timezone.utc),
            volume=data.get("volume", 0),
            has_liquidity=has_liquidity
        )


class KalshiClient:
    """
    Client for fetching Kalshi market data.
    
    Supports both live API and mock mode for development.
    Kalshi requires email/password login to get an access token.
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
        
        # Auth credentials
        self.email = self.config.get("email") or os.getenv("KALSHI_EMAIL")
        self.password = self.config.get("password") or os.getenv("KALSHI_PASSWORD")
        self.api_key = self.config.get("api_key") or os.getenv("KALSHI_API_KEY")
        
        # Session for connection pooling
        self._session = requests.Session()
        self._token: str | None = None
        self._authenticated = False
    
    def _authenticate(self) -> bool:
        """
        Authenticate with Kalshi API.
        
        Returns:
            True if authentication succeeded.
        """
        if self._authenticated and self._token:
            return True
        
        if not self.email or not self.password:
            logger.warning("Kalshi email/password not configured - using mock data")
            return False
        
        try:
            response = self._session.post(
                f"{self.base_url}/login",
                json={"email": self.email, "password": self.password}
            )
            response.raise_for_status()
            data = response.json()
            
            self._token = data.get("token")
            if self._token:
                self._session.headers.update({"Authorization": f"Bearer {self._token}"})
                self._authenticated = True
                logger.info("Successfully authenticated with Kalshi")
                return True
            
        except requests.RequestException as e:
            logger.error(f"Kalshi authentication failed: {e}")
        
        return False
    
    def get_weather_markets(self) -> list[KalshiMarket]:
        """
        Fetch weather-related markets (daily temperature).
        
        Returns:
            List of KalshiMarket objects for weather prediction markets.
        """
        if self.use_mock:
            return self._get_mock_weather_markets()
        
        # Temperature series on Kalshi
        # Format: KXHIGH{CITY} for high temps, KXLOW{CITY} for low temps
        # Note: Some cities have a T prefix (e.g., KXHIGHTBOS, KXHIGHTATL)
        temp_series = [
            # High temperature markets
            "KXHIGHNY",     # NYC high
            "KXHIGHLAX",    # LA high  
            "KXHIGHCHI",    # Chicago high
            "KXHIGHMIA",    # Miami high
            "KXHIGHSF",     # San Francisco high
            "KXHIGHDEN",    # Denver high
            "KXHIGHTBOS",   # Boston high (note: T prefix)
            "KXHIGHPHL",    # Philadelphia high
            "KXHIGHTATL",   # Atlanta high (note: T prefix)
            "KXHIGHPHX",    # Phoenix high
            "KXHIGHNOLA",   # New Orleans high
            "KXHIGHLV",     # Las Vegas high
            "KXHIGHTMSP",   # Minneapolis high (note: T prefix)
            # Low temperature markets
            "KXLOWNY",      # NYC low
            "KXLOWTCHI",    # Chicago low
            "KXLOWDEN",     # Denver low
            "KXLOWTBOS",    # Boston low
            "KXLOWTMSP",    # Minneapolis low
        ]
        
        weather_markets = []
        
        for series_ticker in temp_series:
            markets = self._fetch_markets_by_series(series_ticker)
            weather_markets.extend(markets)
        
        if not weather_markets:
            logger.warning("No weather markets found on Kalshi, using mock data")
            return self._get_mock_weather_markets()
        
        logger.info(f"Found {len(weather_markets)} temperature markets")
        return weather_markets
    
    def _fetch_markets_by_series(self, series_ticker: str) -> list[KalshiMarket]:
        """Fetch all open markets for a series."""
        try:
            response = self._session.get(
                f"{self.base_url}/markets",
                params={"series_ticker": series_ticker, "status": "open", "limit": 50}
            )
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for market_data in data.get("markets", []):
                try:
                    markets.append(KalshiMarket.from_api_response(market_data))
                except (KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed market: {e}")
            
            return markets
            
        except requests.RequestException as e:
            logger.debug(f"Failed to fetch series {series_ticker}: {e}")
            return []
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for market_data in data.get("markets", []):
                try:
                    markets.append(KalshiMarket.from_api_response(market_data))
                except (KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed market: {e}")
            
            return markets
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    
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
        - location: City name
        - threshold_temp: Temperature threshold in Fahrenheit
        - threshold_type: "high_above", "high_below", "low_above", "low_below"
        - is_bucket: True if this is a range bucket (e.g., "30° to 31°")
        
        Kalshi ticker formats:
        - KXHIGHNY-26FEB09-T35 = NYC high >= 36°F (threshold)
        - KXHIGHNY-26FEB09-B30.5 = NYC high in 30-31°F range (bucket)
        - KXLOWDEN-26FEB09-T20 = Denver low >= 21°F
        
        Returns None if parsing fails.
        """
        # Pattern for threshold markets: KXHIGH{CITY}-DATE-T{TEMP}
        # The T value is 1 less than actual threshold (T35 means "36 or above")
        threshold_pattern = r"KX(HIGH|LOW)([A-Z]{2,4})-\d{2}[A-Z]{3}\d{2}-T(\d+)"
        match = re.match(threshold_pattern, market.market_id)
        
        if match:
            high_low = match.group(1).lower()
            city_code = match.group(2)
            # T35 means "36 or above", so add 1
            raw_threshold = int(match.group(3))
            
            # Check question to determine direction
            question_lower = market.question.lower()
            # Check for "below" indicators: "or below", "below", "<"
            is_below = ("or below" in question_lower or 
                       "below" in question_lower or 
                       f"<{raw_threshold}" in question_lower or
                       f"< {raw_threshold}" in question_lower)
            # Check for "above" indicators: "or above", "above", ">"  
            is_above = ("or above" in question_lower or 
                       "above" in question_lower or
                       f">{raw_threshold}" in question_lower or
                       f"> {raw_threshold}" in question_lower)
            
            if is_above and not is_below:
                threshold = raw_threshold + 1  # T35 -> 36 or above
                threshold_type = f"{high_low}_above"
            elif is_below and not is_above:
                threshold = raw_threshold  # T28 with "below" means 27 or below
                threshold_type = f"{high_low}_below"
            else:
                threshold = raw_threshold + 1
                threshold_type = f"{high_low}_above"
            
            city_map = {
                "NY": "New York",
                "LAX": "Los Angeles",
                "LA": "Los Angeles",
                "CHI": "Chicago",
                "MIA": "Miami",
                "SF": "San Francisco",
                "DEN": "Denver",
                "TCHI": "Chicago",
                "ATL": "Atlanta",
                "TATL": "Atlanta",
                "DAL": "Dallas",
                "HOU": "Houston",
                "PHX": "Phoenix",
                "PHL": "Philadelphia",
                "BOS": "Boston",
                "TBOS": "Boston",
                "NOLA": "New Orleans",
                "LV": "Las Vegas",
                "VEG": "Las Vegas",
                "MSP": "Minneapolis",
                "TMSP": "Minneapolis",
                "MIN": "Minneapolis",
            }
            
            return {
                "location": city_map.get(city_code, city_code),
                "threshold_temp": threshold,
                "threshold_type": threshold_type,
                "is_bucket": False
            }
        
        # Pattern for bucket markets: KXHIGH{CITY}-DATE-B{TEMP}
        # B30.5 means "30 to 31" range
        bucket_pattern = r"KX(HIGH|LOW)([A-Z]{2,4})-\d{2}[A-Z]{3}\d{2}-B([\d.]+)"
        match = re.match(bucket_pattern, market.market_id)
        
        if match:
            high_low = match.group(1).lower()
            city_code = match.group(2)
            bucket_mid = float(match.group(3))
            # B30.5 means range 30-31, so lower bound is floor
            lower_bound = int(bucket_mid)
            upper_bound = lower_bound + 1
            
            city_map = {
                "NY": "New York",
                "LAX": "Los Angeles", 
                "LA": "Los Angeles",
                "CHI": "Chicago",
                "MIA": "Miami",
                "SF": "San Francisco",
                "DEN": "Denver",
                "TCHI": "Chicago",
                "ATL": "Atlanta",
                "TATL": "Atlanta",
                "DAL": "Dallas",
                "HOU": "Houston",
                "PHX": "Phoenix",
                "PHL": "Philadelphia",
                "BOS": "Boston",
                "TBOS": "Boston",
                "NOLA": "New Orleans",
                "LV": "Las Vegas",
                "VEG": "Las Vegas",
                "MSP": "Minneapolis",
                "TMSP": "Minneapolis",
                "MIN": "Minneapolis",
            }
            
            return {
                "location": city_map.get(city_code, city_code),
                "threshold_temp": (lower_bound + upper_bound) / 2,  # midpoint
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "threshold_type": f"{high_low}_bucket",
                "is_bucket": True
            }
        
        # Fallback: try old pattern for mock data compatibility
        old_pattern = r"(HIGH|LOW)([A-Z]{2,3})-\d{2}[A-Z]{3}\d{2}-T(\d+)"
        match = re.match(old_pattern, market.market_id)
        
        if match:
            high_low = match.group(1).lower()
            city_code = match.group(2)
            threshold = int(match.group(3))
            
            city_map = {
                "NY": "New York",
                "LA": "Los Angeles",
                "CHI": "Chicago",
                "MIA": "Miami",
                "SF": "San Francisco",
                "DEN": "Denver",
                "TCHI": "Chicago",
                "ATL": "Atlanta",
                "TATL": "Atlanta",
                "DAL": "Dallas",
                "HOU": "Houston",
                "PHX": "Phoenix",
                "PHL": "Philadelphia",
                "BOS": "Boston",
                "TBOS": "Boston",
                "NOLA": "New Orleans",
                "LV": "Las Vegas",
                "VEG": "Las Vegas",
                "MSP": "Minneapolis",
                "TMSP": "Minneapolis",
                "MIN": "Minneapolis",
            }
            
            if "below" in market.question.lower():
                threshold_type = f"{high_low}_below"
            else:
                threshold_type = f"{high_low}_above"
            
            return {
                "location": city_map.get(city_code, city_code),
                "threshold_temp": threshold,
                "threshold_type": threshold_type,
                "is_bucket": False
            }
        
        logger.debug(f"Could not parse market ID: {market.market_id}")
        return None
