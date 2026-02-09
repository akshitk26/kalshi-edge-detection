"""
Weather Probability Model

Computes fair probabilities for weather prediction markets using:
1. Weather forecast data (point estimate)
2. Forecast uncertainty (standard deviation)
3. Normal distribution assumption for temperature

The model is intentionally simple and explainable:
- Given a forecast of X°F ± σ°F
- Compute P(temp > threshold) using the normal CDF

This is a reasonable first-order approximation. Real improvements would include:
- Ensemble model data
- Historical forecast accuracy calibration
- Skewness in temperature distributions
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from edge_engine.data.kalshi_client import KalshiMarket, KalshiClient
from edge_engine.data.weather_client import WeatherData, WeatherClient
from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.models.probability")


@dataclass(frozen=True)
class EdgeResult:
    """
    Result of edge calculation for a single market.
    
    Attributes:
        market: The evaluated market
        market_prob: Implied probability from market price
        fair_prob: Model-derived fair probability
        edge: fair_prob - market_prob (positive = market underprices YES)
        confidence: Confidence score (0-1) based on data quality
        reasoning: Human-readable explanation of the calculation
    """
    market: KalshiMarket
    market_prob: float
    fair_prob: float
    edge: float
    confidence: float
    reasoning: str
    
    @property
    def has_edge(self) -> bool:
        """Returns True if edge is significant (>= 1%)."""
        return abs(self.edge) >= 0.01
    
    @property
    def direction(self) -> str:
        """Returns 'YES' if market underprices, 'NO' if overprices."""
        return "YES" if self.edge > 0 else "NO"


class WeatherProbabilityModel:
    """
    Computes fair probabilities for weather prediction markets.
    
    Uses weather forecast data and assumes normally distributed
    temperature outcomes to compute P(temp > threshold).
    """
    
    def __init__(self, weather_client: WeatherClient, config: dict):
        """
        Initialize the probability model.
        
        Args:
            weather_client: Client for fetching weather data
            config: Configuration dictionary
        """
        self.weather_client = weather_client
        self.config = config
        
        # Confidence decay: reduce confidence for stale data
        self.confidence_decay_hours = config.get("edge", {}).get(
            "confidence_decay_hours", 6
        )
    
    def evaluate_market(self, market: KalshiMarket) -> EdgeResult | None:
        """
        Evaluate a single market and compute edge.
        
        Args:
            market: The Kalshi market to evaluate
        
        Returns:
            EdgeResult if evaluation succeeds, None if data is unavailable
        """
        # Parse market parameters
        params = KalshiClient.parse_market_params(market)
        if not params:
            logger.debug(f"Cannot parse market: {market.market_id}")
            return None
        
        location = params["location"]
        threshold_type = params["threshold_type"]
        is_bucket = params.get("is_bucket", False)
        
        # Fetch weather data
        weather = self.weather_client.get_forecast(location, market.close_time)
        if not weather:
            logger.warning(f"No weather data for {location}")
            return None
        
        # Calculate fair probability
        if is_bucket:
            # Bucket market: P(lower <= temp < upper)
            lower = params["lower_bound"]
            upper = params["upper_bound"]
            fair_prob = self._calculate_bucket_probability(weather, lower, upper, threshold_type)
            threshold = params["threshold_temp"]  # midpoint for display
        else:
            # Threshold market: P(temp > threshold) or P(temp < threshold)
            threshold = params["threshold_temp"]
            fair_prob = self._calculate_probability(weather, threshold, threshold_type)
        
        # Calculate edge
        edge = fair_prob - market.market_prob
        
        # Calculate confidence score
        confidence = self._calculate_confidence(weather, market)
        
        # Build reasoning string
        reasoning = self._build_reasoning(
            weather, threshold, threshold_type, fair_prob, market.market_prob,
            is_bucket=is_bucket,
            lower=params.get("lower_bound"),
            upper=params.get("upper_bound")
        )
        
        logger.debug(
            f"Evaluated {market.market_id}: "
            f"market={market.market_prob:.1%}, fair={fair_prob:.1%}, edge={edge:+.1%}"
        )
        
        return EdgeResult(
            market=market,
            market_prob=market.market_prob,
            fair_prob=fair_prob,
            edge=edge,
            confidence=confidence,
            reasoning=reasoning
        )
    
    def _calculate_probability(
        self, 
        weather: WeatherData, 
        threshold: float, 
        threshold_type: str
    ) -> float:
        """
        Calculate probability of temperature crossing threshold.
        
        Uses normal distribution with forecast as mean and forecast_std as σ.
        
        Args:
            weather: Weather forecast data
            threshold: Temperature threshold (Fahrenheit)
            threshold_type: One of "high_above", "high_below", "low_above", "low_below"
        
        Returns:
            Probability (0-1) of the event occurring
        """
        # Select relevant forecast values based on threshold type
        if threshold_type.startswith("high"):
            forecast_temp = weather.high_temp_f
            std = weather.high_temp_std
        else:
            forecast_temp = weather.low_temp_f
            std = weather.low_temp_std
        
        # Avoid division by zero
        if std <= 0:
            std = 3.0  # Default uncertainty
        
        # Calculate z-score: how many std devs is threshold from forecast?
        z = (threshold - forecast_temp) / std
        
        # Calculate probability using error function approximation
        # P(X > threshold) = 1 - Φ(z) for "above" events
        # P(X < threshold) = Φ(z) for "below" events
        prob_above = 1 - self._normal_cdf(z)
        
        if threshold_type.endswith("above"):
            return prob_above
        else:  # below
            return 1 - prob_above
    
    def _calculate_bucket_probability(
        self,
        weather: WeatherData,
        lower: float,
        upper: float,
        threshold_type: str
    ) -> float:
        """
        Calculate probability of temperature falling within a bucket range.
        
        P(lower <= temp < upper) = Φ(z_upper) - Φ(z_lower)
        
        Args:
            weather: Weather forecast data
            lower: Lower bound of bucket (Fahrenheit)
            upper: Upper bound of bucket (Fahrenheit)
            threshold_type: Starts with "high" or "low"
        
        Returns:
            Probability (0-1) of temperature in range
        """
        if threshold_type.startswith("high"):
            forecast_temp = weather.high_temp_f
            std = weather.high_temp_std
        else:
            forecast_temp = weather.low_temp_f
            std = weather.low_temp_std
        
        if std <= 0:
            std = 3.0
        
        z_lower = (lower - forecast_temp) / std
        z_upper = (upper - forecast_temp) / std
        
        # P(lower <= X < upper) = Φ(z_upper) - Φ(z_lower)
        prob = self._normal_cdf(z_upper) - self._normal_cdf(z_lower)
        
        return max(0.0, min(1.0, prob))
    
    @staticmethod
    def _normal_cdf(z: float) -> float:
        """
        Compute the CDF of the standard normal distribution.
        
        Uses the error function for accurate computation.
        Φ(z) = 0.5 * (1 + erf(z / sqrt(2)))
        """
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))
    
    def _calculate_confidence(self, weather: WeatherData, market: KalshiMarket) -> float:
        """
        Calculate confidence score based on data quality.
        
        Factors:
        1. Data freshness: Decays with age
        2. Forecast horizon: Further out = less confident
        3. Forecast uncertainty: Higher std = less confident
        
        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence
        confidence = 1.0
        
        # Decay for data age
        age_hours = weather.data_age_hours
        if age_hours > 0:
            age_factor = max(0.5, 1.0 - (age_hours / self.confidence_decay_hours) * 0.5)
            confidence *= age_factor
        
        # Decay for forecast horizon
        now = datetime.now(timezone.utc)
        hours_until_close = (market.close_time - now).total_seconds() / 3600
        if hours_until_close > 24:
            horizon_factor = max(0.6, 1.0 - (hours_until_close - 24) / 120)
            confidence *= horizon_factor
        
        # Decay for high uncertainty
        avg_std = (weather.high_temp_std + weather.low_temp_std) / 2
        if avg_std > 4.0:
            uncertainty_factor = max(0.7, 1.0 - (avg_std - 4.0) / 10)
            confidence *= uncertainty_factor
        
        return round(confidence, 3)
    
    def _build_reasoning(
        self,
        weather: WeatherData,
        threshold: float,
        threshold_type: str,
        fair_prob: float,
        market_prob: float,
        is_bucket: bool = False,
        lower: float | None = None,
        upper: float | None = None
    ) -> str:
        """Build human-readable reasoning for the calculation."""
        if threshold_type.startswith("high"):
            temp_type = "high"
            forecast = weather.high_temp_f
            std = weather.high_temp_std
        else:
            temp_type = "low"
            forecast = weather.low_temp_f
            std = weather.low_temp_std
        
        edge = fair_prob - market_prob
        edge_assessment = (
            f"Market {'underprices' if edge > 0 else 'overprices'} YES by {abs(edge):.1%}"
            if abs(edge) >= 0.01
            else "Market is fairly priced"
        )
        
        if is_bucket and lower is not None and upper is not None:
            return (
                f"Forecast {temp_type}: {forecast:.0f}°F ± {std:.1f}°F | "
                f"P({lower:.0f}° ≤ {temp_type} < {upper:.0f}°) = {fair_prob:.1%} | "
                f"Market: {market_prob:.1%} | {edge_assessment}"
            )
        else:
            direction = "above" if threshold_type.endswith("above") else "below"
            return (
                f"Forecast {temp_type}: {forecast:.0f}°F ± {std:.1f}°F | "
                f"P({temp_type} {direction} {threshold:.0f}°F) = {fair_prob:.1%} | "
                f"Market: {market_prob:.1%} | {edge_assessment}"
            )
