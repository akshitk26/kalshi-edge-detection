"""
Weather Data Client

Fetches weather forecast data from OpenWeatherMap API or returns mock data.
Used to compute fair probabilities for weather-related prediction markets.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.data.weather")


@dataclass(frozen=True)
class WeatherData:
    """
    Immutable weather forecast data for a location.
    
    Attributes:
        location: City name
        forecast_date: Date of the forecast
        high_temp_f: Forecasted high temperature (Fahrenheit)
        low_temp_f: Forecasted low temperature (Fahrenheit)
        high_temp_std: Standard deviation of high temp forecast (Fahrenheit)
        low_temp_std: Standard deviation of low temp forecast (Fahrenheit)
        source: Data source identifier
        fetched_at: When this data was retrieved
    """
    location: str
    forecast_date: datetime
    high_temp_f: float
    low_temp_f: float
    high_temp_std: float  # Uncertainty estimate
    low_temp_std: float   # Uncertainty estimate
    source: str
    fetched_at: datetime
    
    @property
    def data_age_hours(self) -> float:
        """How old this data is in hours."""
        delta = datetime.now(timezone.utc) - self.fetched_at
        return delta.total_seconds() / 3600


class WeatherClient:
    """
    Client for fetching weather forecast data.
    
    Supports OpenWeatherMap API and mock mode.
    """
    
    # City coordinates for API calls
    CITY_COORDS = {
        "New York": (40.7128, -74.0060),
        "Los Angeles": (34.0522, -118.2437),
        "Chicago": (41.8781, -87.6298),
        "Miami": (25.7617, -80.1918),
        "Seattle": (47.6062, -122.3321),
        "Denver": (39.7392, -104.9903),
        "Atlanta": (33.7490, -84.3880),
        "Dallas": (32.7767, -96.7970),
        "Houston": (29.7604, -95.3698),
        "Phoenix": (33.4484, -112.0740),
        "Philadelphia": (39.9526, -75.1652),
        "San Francisco": (37.7749, -122.4194),
        "Boston": (42.3601, -71.0589),
        "NYC": (40.7128, -74.0060),
        "LA": (34.0522, -118.2437),
    }
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize the weather client.
        
        Args:
            config: Configuration dictionary with weather settings.
        """
        self.config = config.get("weather", {})
        self.base_url = self.config.get("base_url", "https://api.openweathermap.org/data/2.5")
        self.use_mock = self.config.get("use_mock", True)
        self.api_key = self.config.get("api_key") or os.getenv("OPENWEATHER_API_KEY")
        
        self._session = requests.Session()
        self._cache: dict[str, WeatherData] = {}
    
    def get_forecast(self, location: str, target_date: datetime | None = None) -> WeatherData | None:
        """
        Get weather forecast for a location.
        
        Args:
            location: City name (e.g., "New York", "NYC")
            target_date: Date for forecast (defaults to tomorrow)
        
        Returns:
            WeatherData if available, None otherwise.
        """
        # Normalize location name
        location = self._normalize_location(location)
        
        if self.use_mock:
            return self._get_mock_forecast(location, target_date)
        
        return self._fetch_forecast(location, target_date)
    
    def _normalize_location(self, location: str) -> str:
        """Normalize location names to standard format."""
        aliases = {
            "NYC": "New York",
            "NY": "New York",
            "LA": "Los Angeles",
            "CHI": "Chicago",
        }
        return aliases.get(location.upper(), location)
    
    def _fetch_forecast(self, location: str, target_date: datetime | None) -> WeatherData | None:
        """Fetch forecast from OpenWeatherMap API."""
        if not self.api_key:
            logger.error("No OpenWeatherMap API key configured")
            return None
        
        coords = self.CITY_COORDS.get(location)
        if not coords:
            logger.error(f"Unknown location: {location}")
            return None
        
        lat, lon = coords
        
        try:
            # Use 5-day forecast endpoint
            response = self._session.get(
                f"{self.base_url}/forecast",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": self.api_key,
                    "units": "imperial"  # Fahrenheit
                }
            )
            response.raise_for_status()
            data = response.json()
            
            return self._parse_forecast(location, data, target_date)
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch weather for {location}: {e}")
            return None
    
    def _parse_forecast(
        self, 
        location: str, 
        data: dict[str, Any], 
        target_date: datetime | None
    ) -> WeatherData | None:
        """Parse OpenWeatherMap API response into WeatherData."""
        now = datetime.now(timezone.utc)
        
        if target_date is None:
            # Default to tomorrow
            target_date = now.replace(hour=12, minute=0, second=0, microsecond=0)
            target_date = target_date.replace(day=target_date.day + 1)
        
        # Find forecasts for target date
        temps = []
        for item in data.get("list", []):
            dt = datetime.fromisoformat(item["dt_txt"].replace(" ", "T") + "+00:00")
            if dt.date() == target_date.date():
                temps.append(item["main"]["temp"])
        
        if not temps:
            logger.warning(f"No forecast data for {location} on {target_date.date()}")
            return None
        
        # Estimate high/low from 3-hour forecasts
        high_temp = max(temps)
        low_temp = min(temps)
        
        # Standard deviation estimate (weather models typically have ~2-4°F error)
        # Increases with forecast horizon
        hours_ahead = (target_date - now).total_seconds() / 3600
        base_std = 2.5
        std_per_day = 0.8
        forecast_std = base_std + (hours_ahead / 24) * std_per_day
        
        return WeatherData(
            location=location,
            forecast_date=target_date,
            high_temp_f=high_temp,
            low_temp_f=low_temp,
            high_temp_std=forecast_std,
            low_temp_std=forecast_std,
            source="openweathermap",
            fetched_at=now
        )
    
    def _get_mock_forecast(self, location: str, target_date: datetime | None) -> WeatherData | None:
        """
        Generate realistic mock weather data.
        
        Mock data is designed to create testable edge scenarios:
        - Some forecasts will align with market prices
        - Some will diverge, creating edge opportunities
        """
        now = datetime.now(timezone.utc)
        
        if target_date is None:
            target_date = now.replace(hour=12, minute=0, second=0, microsecond=0)
        
        # Mock forecasts with realistic February 2026 values
        # Based on typical winter temperatures for each city
        # These should roughly align with Kalshi market expectations
        mock_forecasts = {
            "New York": {
                "high": 31.0,  # Cold February day in NYC
                "low": 22.0,
                "high_std": 3.0,
                "low_std": 2.5
            },
            "Los Angeles": {
                "high": 72.0,  # Mild LA winter
                "low": 54.0,
                "high_std": 2.5,
                "low_std": 2.0
            },
            "Chicago": {
                "high": 28.0,  # Cold Chicago February
                "low": 18.0,
                "high_std": 4.0,
                "low_std": 3.5
            },
            "Miami": {
                "high": 79.0,
                "low": 68.0,
                "high_std": 2.0,
                "low_std": 2.0
            },
            "San Francisco": {
                "high": 58.0,
                "low": 48.0,
                "high_std": 2.5,
                "low_std": 2.0
            },
            "Denver": {
                "high": 42.0,
                "low": 24.0,
                "high_std": 5.0,  # Mountain weather is more variable
                "low_std": 4.5
            }
        }
        
        forecast = mock_forecasts.get(location)
        if not forecast:
            logger.warning(f"No mock forecast available for {location}")
            return None
        
        logger.debug(f"Generated mock forecast for {location}: high={forecast['high']}°F")
        
        return WeatherData(
            location=location,
            forecast_date=target_date,
            high_temp_f=forecast["high"],
            low_temp_f=forecast["low"],
            high_temp_std=forecast["high_std"],
            low_temp_std=forecast["low_std"],
            source="mock",
            fetched_at=now
        )
