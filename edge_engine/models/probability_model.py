"""
Weather Probability Model - Production Calibrated
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import math
from edge_engine.data.kalshi_client import KalshiMarket, KalshiClient
from edge_engine.data.weather_client import WeatherData, WeatherClient
from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.models.probability")


@dataclass(frozen=True)
class EdgeResult:
    market: KalshiMarket
    market_prob: float
    fair_prob: float
    edge: float
    confidence: float
    reasoning: str
    direction: str


class WeatherProbabilityModel:
    # RESTORED: Your original detailed reporting noise table
    REPORTING_NOISE = {
        "San Francisco": 2.5,
        "Los Angeles": 2.0,
        "Miami": 2.0,
        "Boston": 1.8,
        "Seattle": 1.8,
        "New Orleans": 1.8,
        "New York": 1.5,
        "Philadelphia": 1.5,
        "Atlanta": 1.5,
        "Chicago": 1.5,
        "Minneapolis": 1.5,
        "Houston": 1.5,
        "Dallas": 1.5,
        "Denver": 1.5,
        "Phoenix": 1.2,
        "Las Vegas": 1.2,
    }
    DEFAULT_NOISE = 1.5

    def __init__(self, weather_client: WeatherClient, config: dict | None):
        self.weather_client = weather_client
        self.config = config or {}

    def evaluate_market(self, market: KalshiMarket) -> EdgeResult | None:
        params = KalshiClient.parse_market_params(market)
        if not params:
            return None

        # Correct date extraction from ticker
        ticker_parts = market.market_id.split("-")
        if len(ticker_parts) >= 2:
            try:
                weather_date = datetime.strptime(ticker_parts[1], "%y%b%d").replace(
                    tzinfo=timezone.utc
                )
            except:
                weather_date = market.close_time - timedelta(days=1)
        else:
            weather_date = market.close_time - timedelta(days=1)

        weather = self.weather_client.get_forecast(params["location"], weather_date)
        if not weather:
            return None

        # 1. Base statistical probability (using your discrete PMF logic)
        if params.get("is_bucket"):
            fair_prob = self._calculate_bucket_probability(weather, params)
        else:
            fair_prob = self._calculate_threshold_probability(weather, params)

        # 2. Reality Floor: Overwrite stats with hard facts if it's "Today"
        if weather.current_temp_f is not None:
            current = weather.current_temp_f
            if "high" in params["threshold_type"]:
                if params.get("is_bucket"):
                    if current >= params["upper_bound"]:
                        fair_prob = 0.0
                    elif current >= params["lower_bound"]:
                        fair_prob = max(fair_prob, 0.7)
                else:
                    thresh = params["threshold_temp"]
                    if "above" in params["threshold_type"] and current > thresh:
                        fair_prob = 1.0
                    elif "below" in params["threshold_type"] and current >= thresh:
                        fair_prob = 0.0

        edge = fair_prob - market.market_prob
        direction = "BUY YES" if edge > 0 else "BUY NO"

        # Build reasoning
        reasoning = f"Forecast: {weather.high_temp_f:.1f}°F"
        if weather.current_temp_f is not None:
            reasoning += f" (Current: {weather.current_temp_f:.1f}°F)"

        return EdgeResult(
            market=market,
            market_prob=market.market_prob,
            fair_prob=fair_prob,
            edge=edge,
            confidence=0.8,
            reasoning=reasoning,
            direction=direction,
        )

    # --- RESTORED: All original math functions ---
    def _get_effective_std(self, forecast_std, location):
        sigma_rpt = self.REPORTING_NOISE.get(location, self.DEFAULT_NOISE)
        sigma_fc = max(forecast_std, 0.5)
        return math.sqrt(sigma_fc**2 + sigma_rpt**2)

    def _calculate_bucket_probability(self, weather, params):
        mu = (
            weather.high_temp_f
            if "high" in params["threshold_type"]
            else weather.low_temp_f
        )
        std = self._get_effective_std(weather.high_temp_std, weather.location)
        k = int(params["lower_bound"])
        return self._normal_cdf((k + 0.5 - mu) / std) - self._normal_cdf(
            (k - 0.5 - mu) / std
        )

    def _calculate_threshold_probability(self, weather, params):
        mu = (
            weather.high_temp_f
            if "high" in params["threshold_type"]
            else weather.low_temp_f
        )
        std = self._get_effective_std(weather.high_temp_std, weather.location)
        thresh = params["threshold_temp"]
        if "above" in params["threshold_type"]:
            return 1 - self._normal_cdf((thresh - 0.5 - mu) / std)
        return self._normal_cdf((thresh + 0.5 - mu) / std)

    @staticmethod
    def _normal_cdf(z):
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))
