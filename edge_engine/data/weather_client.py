"""
Weather Data Client - Full Production Version
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
    location: str
    forecast_date: datetime
    high_temp_f: float
    low_temp_f: float
    high_temp_std: float
    low_temp_std: float
    source: str
    fetched_at: datetime
    # ADDED: This field is required for the "Reality Floor" logic
    current_temp_f: float | None = None 
    
    @property
    def data_age_hours(self) -> float:
        delta = datetime.now(timezone.utc) - self.fetched_at
        return delta.total_seconds() / 3600

class WeatherClient:
    # RESTORED: All your original city coordinates + exact station coordinates for settlement
    CITY_COORDS = {
        "New York": (40.7789, -73.9692), # Central Park Station (Settlement)
        "Los Angeles": (33.9416, -118.4085), # LAX Airport (Settlement)
        "Chicago": (41.9742, -87.9073), # O'Hare (Settlement)
        "Miami": (25.7959, -80.2870),
        "Seattle": (47.4489, -122.3094),
        "Denver": (39.8561, -104.6737),
        "Atlanta": (33.6407, -84.4277),
        "Dallas": (32.8998, -97.0403),
        "Houston": (29.9902, -95.3368),
        "Phoenix": (33.4342, -112.0081),
        "Philadelphia": (39.8721, -75.2411),
        "San Francisco": (37.6213, -122.3790),
        "Boston": (42.3601, -71.0589),
        "New Orleans": (29.9911, -90.2592),
        "Las Vegas": (36.0840, -115.1537),
        "Minneapolis": (44.8848, -93.2223),
        "NYC": (40.7789, -73.9692),
        "LA": (33.9416, -118.4085),
    }
    
    def __init__(self, config: dict[str, Any]):
        self.config = config.get("weather", {})
        self.base_url = self.config.get("base_url", "https://api.openweathermap.org/data/2.5")
        self.use_mock = self.config.get("use_mock", False)
        self.api_key = self.config.get("api_key") or os.getenv("OPENWEATHER_API_KEY")
        self._session = requests.Session()

    def get_forecast(self, location: str, target_date: datetime) -> WeatherData | None:
        location = self._normalize_location(location)
        if self.use_mock:
            return self._get_mock_forecast(location, target_date)
        
        # 1. Fetch main forecast
        forecast_data = self._fetch_forecast(location, target_date)
        if not forecast_data:
            return None

        # 2. Fetch current observation if target is TODAY
        current_obs = None
        if target_date.date() == datetime.now(timezone.utc).date():
            current_obs = self._fetch_current_temp(location)

        # 3. Combine into final object
        return WeatherData(
            location=forecast_data.location,
            forecast_date=forecast_data.forecast_date,
            high_temp_f=forecast_data.high_temp_f,
            low_temp_f=forecast_data.low_temp_f,
            high_temp_std=forecast_data.high_temp_std,
            low_temp_std=forecast_data.low_temp_std,
            source=forecast_data.source,
            fetched_at=forecast_data.fetched_at,
            current_temp_f=current_obs
        )

    def _fetch_current_temp(self, location: str) -> float | None:
        coords = self.CITY_COORDS.get(location)
        if not coords or not self.api_key: return None
        try:
            resp = self._session.get(f"{self.base_url}/weather", params={
                "lat": coords[0], "lon": coords[1], "appid": self.api_key, "units": "imperial"
            })
            return resp.json().get("main", {}).get("temp")
        except Exception as e:
            logger.error(f"Error fetching current temp for {location}: {e}")
            return None

    def _fetch_forecast(self, location: str, target_date: datetime) -> WeatherData | None:
        coords = self.CITY_COORDS.get(location)
        if not coords: return None
        try:
            resp = self._session.get(f"{self.base_url}/forecast", params={
                "lat": coords[0], "lon": coords[1], "appid": self.api_key, "units": "imperial"
            })
            resp.raise_for_status()
            return self._parse_forecast(location, resp.json(), target_date)
        except Exception as e:
            logger.error(f"Forecast fetch error: {e}")
            return None

    def _normalize_location(self, loc: str) -> str:
        aliases = {"NYC": "New York", "NY": "New York", "LA": "Los Angeles", "CHI": "Chicago"}
        return aliases.get(loc.upper(), loc)

    def _parse_forecast(self, location, data, target_date):
        now = datetime.now(timezone.utc)
        temps = [i["main"]["temp"] for i in data.get("list", []) 
                 if datetime.fromtimestamp(i["dt"], tz=timezone.utc).date() == target_date.date()]
        if not temps: return None
        
        # Dynamic std based on horizon (original logic restored)
        hours_ahead = (target_date - now).total_seconds() / 3600
        forecast_std = 1.0 if hours_ahead <= 12 else 1.5 if hours_ahead <= 24 else 2.5

        return WeatherData(
            location=location, forecast_date=target_date,
            high_temp_f=max(temps), low_temp_f=min(temps),
            high_temp_std=forecast_std, low_temp_std=forecast_std,
            source="openweathermap", fetched_at=now
        )

    def _get_mock_forecast(self, location, target_date):
        # Full mock set restored for testing
        mock_data = {"New York": 31.0, "Los Angeles": 72.0, "Chicago": 39.0, "Denver": 70.5}
        val = mock_data.get(location, 50.0)
        return WeatherData(
            location=location, forecast_date=target_date,
            high_temp_f=val, low_temp_f=val-10,
            high_temp_std=1.5, low_temp_std=1.5,
            source="mock", fetched_at=datetime.now(timezone.utc),
            current_temp_f=val-1 if target_date.date() == datetime.now().date() else None
        )