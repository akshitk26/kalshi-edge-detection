"""
Weather Probability Model — Discrete Reported Temperature

Kalshi temperature markets settle on the integer value from the
NWS Climatological Report (Daily). This is a DISCRETE outcome
measured at a specific station, not a continuous forecast model output.

Two-component uncertainty model:

    σ²_effective = σ²_forecast + σ²_reporting

  • σ_forecast: Weather model's uncertainty about the atmospheric temp.
    This is what APIs return (typically 1–3°F depending on horizon).

  • σ_reporting: "Representation error" — the gap between the forecast
    model's grid-point temperature and what the NWS station actually
    reports. Captures:
      – Station vs. grid-point mismatch
      – Max-of-day aggregation (daily high ≠ single model snapshot)
      – Microclimate / marine layer effects (coastal cities)
      – NWS rounding / reporting conventions
      – Station-specific biases and integer stickiness
    City-specific; typically 1.0–2.5°F, higher for coastal stations.

From the effective distribution T ~ N(μ, σ²_eff) we derive a discrete
PMF over integer reported temperatures:

    P(reported = k) = Φ((k+0.5−μ)/σ_eff) − Φ((k−0.5−μ)/σ_eff)

This correctly models both bucket and threshold markets.
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
    
    Models the distribution of NWS-reported integer temperatures using
    a two-component σ (forecast uncertainty + station reporting noise),
    then derives a discrete PMF over integers.
    """
    
    # --- Station reporting noise (σ_reporting) ---
    # This is the "representation error" between the forecast model's
    # grid-point temperature and the integer the NWS station reports.
    # Based on NWS verification statistics and station characteristics.
    #
    # Higher values for:
    #   - Coastal cities (marine layer timing, onshore/offshore flow)
    #   - Cities where microclimate dominates (SF, LA basin)
    #   - Stations with known integer-stickiness in records
    # Lower values for:
    #   - Continental cities with well-mixed boundary layers
    #   - Stations that closely match model grid representation
    REPORTING_NOISE: dict[str, float] = {
        # Coastal / marine-layer cities: high representation error
        "San Francisco": 2.5,  # Extreme microclimate, fog/marine layer timing
        "Los Angeles":   2.0,  # Basin effects, coastal vs inland variance
        "Miami":         2.0,  # Sea-breeze timing, marine influence
        "Boston":        1.8,  # Coastal, harbor effects
        "Seattle":       1.8,  # Puget Sound marine influence
        "New Orleans":   1.8,  # Gulf proximity, humidity effects on max
        # Continental cities: moderate representation error
        "New York":      1.5,  # Urban heat island, Central Park station
        "Philadelphia":  1.5,
        "Atlanta":       1.5,
        "Chicago":       1.5,
        "Minneapolis":   1.5,
        "Houston":       1.5,
        "Dallas":        1.5,
        # Arid / clear-sky cities: lower (forecasts are good) but station effects persist
        "Denver":        1.5,  # Altitude, chinook effects can surprise
        "Phoenix":       1.2,  # Very predictable, but station siting matters
        "Las Vegas":     1.2,  # Arid, stable, low representation error
    }
    DEFAULT_REPORTING_NOISE = 1.5  # Fallback for unknown cities
    
    def __init__(self, weather_client: WeatherClient, config: dict | None):
        """
        Initialize the probability model.
        
        Args:
            weather_client: Client for fetching weather data
            config: Configuration dictionary
        """
        self.weather_client = weather_client
        self.config = config if isinstance(config, dict) else {}
        
        # Allow config overrides for reporting noise
        model_config = self.config.get("model") or {}
        self.reporting_noise_overrides = model_config.get("reporting_noise", {})
        
        # Confidence decay: reduce confidence for stale data
        edge_config = self.config.get("edge") or {}
        self.confidence_decay_hours = edge_config.get("confidence_decay_hours", 6)
    
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
            fair_prob_raw = self._calculate_bucket_probability(weather, lower, upper, threshold_type)
            threshold = params["threshold_temp"]  # midpoint for display
        else:
            # Threshold market: P(temp > threshold) or P(temp < threshold)
            threshold = params["threshold_temp"]
            fair_prob_raw = self._calculate_probability(weather, threshold, threshold_type)
        
        # Calculate confidence score
        confidence = self._calculate_confidence(weather, market)
        
        # === TRADER SAFEGUARDS ===
        # Apply confidence-weighted edge calculation
        # to prevent unrealistic edges from naive statistical models
        
        # Use raw probability as fair value
        fair_prob = fair_prob_raw
        
        # 1. Calculate confidence-weighted edge
        #    Don't claim huge edges when confidence is low
        #    A 50% edge with 30% confidence shouldn't trigger trades
        raw_edge = fair_prob - market.market_prob
        edge = raw_edge * confidence
        
        # 2. Extreme market guardrail
        #    Markets at 1-10% or 90-100% require high confidence to override
        #    Prevents false signals from statistical tail probabilities
        is_extreme_market = market.market_prob < 0.10 or market.market_prob > 0.90
        if is_extreme_market and confidence < 0.8:
            # Suppress edge for extreme markets unless we're very confident
            # These markets are often correctly priced by informed traders
            edge = 0.0
        
        # 3. Extreme edge guardrail (data quality check)
        #    Edges >50% are almost always data issues, not real opportunities
        #    Suppress these unless market has strong liquidity
        if abs(raw_edge) > 0.50:
            # Only trust extreme edges if market is liquid
            if not market.has_liquidity or market.market_prob < 0.02:
                edge = 0.0
        elif abs(raw_edge) > 0.30:
            # Dampen medium-large edges when liquidity is poor
            if not market.has_liquidity:
                edge = edge * 0.3
        
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
    
    def _get_reporting_noise(self, location: str) -> float:
        """
        Get the station reporting noise (σ_reporting) for a city.
        
        Checks config overrides first, then the built-in table.
        
        Args:
            location: City name
        
        Returns:
            σ_reporting in °F
        """
        # Config override takes precedence
        if location in self.reporting_noise_overrides:
            return float(self.reporting_noise_overrides[location])
        return self.REPORTING_NOISE.get(location, self.DEFAULT_REPORTING_NOISE)
    
    def _get_effective_std(
        self, 
        forecast_std: float, 
        location: str
    ) -> tuple[float, float, float]:
        """
        Compute the effective σ for the reported-temperature distribution.
        
            σ²_eff = σ²_forecast + σ²_reporting
        
        This is the standard representation-error decomposition from
        data assimilation / forecast verification literature.
        
        Args:
            forecast_std: The forecast model's uncertainty (σ_forecast)
            location: City name (for station-specific reporting noise)
        
        Returns:
            (sigma_effective, sigma_forecast, sigma_reporting) tuple
        """
        sigma_reporting = self._get_reporting_noise(location)
        sigma_forecast = max(forecast_std, 0.5)  # Floor: forecast can't be perfect
        sigma_eff = math.sqrt(sigma_forecast ** 2 + sigma_reporting ** 2)
        return sigma_eff, sigma_forecast, sigma_reporting
    
    def _discrete_integer_prob(
        self,
        forecast_temp: float,
        std: float,
        k: int
    ) -> float:
        """
        Probability that the NWS reports integer temperature k.
        
        Uses the effective σ (already combining forecast + reporting noise):
        
            P(reported = k) = Φ((k + 0.5 − μ) / σ_eff) − Φ((k − 0.5 − μ) / σ_eff)
        
        Args:
            forecast_temp: Forecast mean (μ) in Fahrenheit
            std: Effective standard deviation (σ_eff), NOT raw forecast σ
            k: The integer temperature value
        
        Returns:
            Probability (0-1) that the NWS reports exactly k°F
        """
        z_upper = (k + 0.5 - forecast_temp) / std
        z_lower = (k - 0.5 - forecast_temp) / std
        return self._normal_cdf(z_upper) - self._normal_cdf(z_lower)

    def _calculate_probability(
        self, 
        weather: WeatherData, 
        threshold: float, 
        threshold_type: str
    ) -> float:
        """
        Probability that the NWS-reported integer temperature crosses a threshold.
        
        Uses σ_effective (forecast + reporting noise) in the discrete model:
        - "above" (reported ≥ T): P = 1 − Φ((T − 0.5 − μ) / σ_eff)
        - "below" (reported ≤ T): P = Φ((T + 0.5 − μ) / σ_eff)
        """
        if threshold_type.startswith("high"):
            forecast_temp = weather.high_temp_f
            forecast_std = weather.high_temp_std
        else:
            forecast_temp = weather.low_temp_f
            forecast_std = weather.low_temp_std
        
        std_eff, _, _ = self._get_effective_std(forecast_std, weather.location)
        
        if threshold_type.endswith("above"):
            z = (threshold - 0.5 - forecast_temp) / std_eff
            return 1 - self._normal_cdf(z)
        else:  # below
            z = (threshold + 0.5 - forecast_temp) / std_eff
            return self._normal_cdf(z)
    
    def _calculate_bucket_probability(
        self,
        weather: WeatherData,
        lower: float,
        upper: float,
        threshold_type: str
    ) -> float:
        """
        Probability for a bucket market — a SINGLE discrete integer outcome.
        
        Kalshi bucket "72° to 73°" settles YES iff the NWS reports exactly
        the integer temperature = lower_bound (72).
        
        Uses σ_effective (forecast + reporting noise) so that a centered
        1°F bucket gets realistic mass (~15–20% for typical σ_eff ≈ 2–2.5°F)
        rather than the inflated values from using raw forecast σ alone.
        
        Args:
            weather: Weather forecast data
            lower: The integer temperature this bucket represents
            upper: Upper label (lower + 1); not used in calculation
            threshold_type: Starts with "high" or "low"
        
        Returns:
            Probability (0-1) that NWS reports exactly lower°F
        """
        if threshold_type.startswith("high"):
            forecast_temp = weather.high_temp_f
            forecast_std = weather.high_temp_std
        else:
            forecast_temp = weather.low_temp_f
            forecast_std = weather.low_temp_std
        
        std_eff, _, _ = self._get_effective_std(forecast_std, weather.location)
        
        return self._discrete_integer_prob(forecast_temp, std_eff, int(lower))
    
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
        
        # Show effective σ decomposition for transparency
        std_eff, sigma_fc, sigma_rpt = self._get_effective_std(std, weather.location)
        sigma_str = f"σ_eff={std_eff:.1f}°F (σ_fc={sigma_fc:.1f} + σ_rpt={sigma_rpt:.1f})"
        
        if is_bucket and lower is not None and upper is not None:
            return (
                f"Forecast {temp_type}: {forecast:.0f}°F | {sigma_str} | "
                f"P(reported = {lower:.0f}°F) = {fair_prob:.1%} | "
                f"Market: {market_prob:.1%} | {edge_assessment}"
            )
        else:
            direction = "above" if threshold_type.endswith("above") else "below"
            return (
                f"Forecast {temp_type}: {forecast:.0f}°F | {sigma_str} | "
                f"P(reported {direction} {threshold:.0f}°F) = {fair_prob:.1%} | "
                f"Market: {market_prob:.1%} | {edge_assessment}"
            )
