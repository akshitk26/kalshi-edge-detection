"""
Kalshi Market Data Client - Fixed Parsing
"""

import base64
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.data.kalshi")

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("cryptography not installed — portfolio features disabled")


@dataclass(frozen=True)
class KalshiMarket:
    market_id: str
    question: str
    yes_price: int
    market_prob: float
    close_time: datetime
    category: str
    fetched_at: datetime
    volume: int = 0
    has_liquidity: bool = True
    # Raw bid/ask for hedge calculator
    yes_bid: int = 0
    yes_ask: int = 0
    no_bid: int = 0
    no_ask: int = 0

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], price_source: str = "last_price"
    ) -> "KalshiMarket":
        raw_yes_bid = data.get("yes_bid", 0) or 0
        raw_yes_ask = data.get("yes_ask", 0) or 0
        last_price = data.get("last_price", 0) or 0
        raw_no_bid = data.get("no_bid", 0) or 0
        raw_no_ask = data.get("no_ask", 0) or 0

        # Derive NO prices from YES if not provided by API
        if raw_no_bid == 0 and raw_yes_ask > 0:
            raw_no_bid = 100 - raw_yes_ask
        if raw_no_ask == 0 and raw_yes_bid > 0:
            raw_no_ask = 100 - raw_yes_bid

        # Liquidity check
        has_liquidity = (
            raw_yes_bid > 0 and raw_yes_ask > 0 and (raw_yes_ask - raw_yes_bid) <= 15
        )

        # Determine price
        if price_source == "yes_ask":
            yes_price = raw_yes_ask or last_price or raw_yes_bid
        elif price_source == "mid":
            if raw_yes_bid > 0 and raw_yes_ask > 0:
                yes_price = (raw_yes_bid + raw_yes_ask) // 2
            else:
                yes_price = last_price or raw_yes_ask or raw_yes_bid
        else:
            yes_price = last_price or raw_yes_ask or raw_yes_bid

        # Default to 50 cents if essentially no data, to avoid 0% math errors later
        if yes_price == 0 and not has_liquidity:
            yes_price = 50

        title = data.get("title", "")
        subtitle = data.get("subtitle", "")
        question = f"{title}: {subtitle}" if subtitle else title

        return cls(
            market_id=data["ticker"],
            question=question,
            yes_price=yes_price,
            market_prob=yes_price / 100.0,
            close_time=datetime.fromisoformat(
                data["close_time"].replace("Z", "+00:00")
            ),
            category=data.get("category", "unknown"),
            fetched_at=datetime.now(timezone.utc),
            volume=data.get("volume", 0),
            has_liquidity=has_liquidity,
            yes_bid=raw_yes_bid,
            yes_ask=raw_yes_ask,
            no_bid=raw_no_bid,
            no_ask=raw_no_ask,
        )


class KalshiClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config.get("kalshi", {})
        self.base_url = self.config.get(
            "base_url", "https://api.elections.kalshi.com/trade-api/v2"
        )
        self.use_mock = self.config.get("use_mock", False)
        self.price_source = self.config.get("price_source", "last_price")
        self._session = requests.Session()

        self._api_key_id: str | None = self.config.get("api_key_id")
        self._private_key = None
        key_path = self.config.get("private_key_path")
        if key_path and HAS_CRYPTO:
            self._private_key = self._load_private_key(key_path)
            if self._private_key:
                logger.info("Kalshi API key loaded — portfolio features enabled")

    @property
    def has_auth(self) -> bool:
        return self._api_key_id is not None and self._private_key is not None

    @staticmethod
    def _load_private_key(path: str):
        """Load RSA private key from PEM file."""
        try:
            key_path = Path(path).expanduser()
            pem_data = key_path.read_bytes()
            return serialization.load_pem_private_key(pem_data, password=None)
        except Exception as e:
            logger.error(f"Failed to load private key from {path}: {e}")
            return None

    def _sign_request(self, method: str, path: str) -> dict[str, str]:
        """Generate RSA-PSS auth headers for an authenticated request."""
        if not self.has_auth:
            raise RuntimeError("API key not configured")

        timestamp_ms = str(int(time.time() * 1000))
        message = f"{timestamp_ms}{method}{path}"
        signature = self._private_key.sign(
            message.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }

    def _authenticated_get(self, path: str, params: dict | None = None) -> dict:
        """Perform an authenticated GET request to the Kalshi API."""
        headers = self._sign_request("GET", f"/trade-api/v2{path}")
        resp = self._session.get(
            f"{self.base_url}{path}", headers=headers, params=params
        )
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> dict[str, Any]:
        """Fetch account balance and portfolio value (in cents)."""
        data = self._authenticated_get("/portfolio/balance")
        return {
            "balance": data.get("balance", 0),
            "portfolio_value": data.get("portfolio_value", 0),
            "total_value": data.get("balance", 0) + data.get("portfolio_value", 0),
            "updated_ts": data.get("updated_ts", 0),
        }

    def get_positions(self) -> list[dict[str, Any]]:
        """Fetch all open market positions with pagination."""
        all_positions: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {
                "limit": 200,
                "count_filter": "position",
            }
            if cursor:
                params["cursor"] = cursor
            data = self._authenticated_get("/portfolio/positions", params)
            for mp in data.get("market_positions", []):
                all_positions.append({
                    "ticker": mp.get("ticker", ""),
                    "position": mp.get("position", 0),
                    "market_exposure": mp.get("market_exposure", 0),
                    "market_exposure_dollars": mp.get("market_exposure_dollars", "0"),
                    "realized_pnl": mp.get("realized_pnl", 0),
                    "realized_pnl_dollars": mp.get("realized_pnl_dollars", "0"),
                    "fees_paid": mp.get("fees_paid", 0),
                    "total_traded": mp.get("total_traded", 0),
                })
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return all_positions

    def get_fills(self) -> list[dict[str, Any]]:
        """Fetch all trade fills (every matched trade) with pagination."""
        all_fills: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._authenticated_get("/portfolio/fills", params)
            all_fills.extend(data.get("fills", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return all_fills

    def get_settlements(self) -> list[dict[str, Any]]:
        """Fetch all settlement records with pagination."""
        all_settlements: list[dict[str, Any]] = []
        cursor = ""
        while True:
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._authenticated_get("/portfolio/settlements", params)
            all_settlements.extend(data.get("settlements", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return all_settlements

    def get_weather_markets(self) -> list[KalshiMarket]:
        # Fetch markets for all supported cities
        temp_series = [
            "KXHIGHNY",
            "KXHIGHCHI",
            "KXHIGHDEN",
            "KXHIGHTATL",
            "KXHIGHLAX",
            "KXHIGHMIA",
            "KXHIGHTBOS",
            "KXHIGHPHL",
            "KXHIGHPHX",
        ]
        weather_markets = []
        for series in temp_series:
            weather_markets.extend(self._fetch_markets_by_series(series))
        return weather_markets

    def _fetch_markets_by_series(self, series_ticker: str) -> list[KalshiMarket]:
        try:
            response = self._session.get(
                f"{self.base_url}/markets",
                params={"series_ticker": series_ticker, "status": "open", "limit": 100},
            )
            response.raise_for_status()
            data = response.json()
            return [
                KalshiMarket.from_api_response(m, self.price_source)
                for m in data.get("markets", [])
            ]
        except Exception as e:
            logger.error(f"Error fetching {series_ticker}: {e}")
            return []

    @staticmethod
    def parse_market_params(market: KalshiMarket) -> dict[str, Any] | None:
        """
        Robustly parses Kalshi weather tickers and subtitles.
        """
        # 1. BUCKET MARKETS (e.g., KXHIGHNY-26FEB14-B46.5)
        # B46.5 usually means the band 46.0 to 46.99 (or just integer 46)
        bucket_pattern = r"KX(HIGH|LOW)([A-Z]{2,5})-\d{2}[A-Z]{3}\d{2}-B([\d.]+)"
        match = re.search(bucket_pattern, market.market_id)
        if match:
            high_low = match.group(1).lower()
            city_code = match.group(2)
            val = float(match.group(3))

            # If val ends in .5, it's typically the range [floor, floor+1]
            lower = int(val)
            upper = lower + 1

            return {
                "location": KalshiClient._map_city(city_code),
                "threshold_temp": val,
                "lower_bound": lower,
                "upper_bound": upper,
                "threshold_type": f"{high_low}_bucket",
                "is_bucket": True,
            }

        # 2. THRESHOLD MARKETS (e.g., KXHIGHNY-26FEB14-T40)
        # T40 might mean > 40 OR < 40 depending on the subtitle.
        threshold_pattern = (
            r"KX(HIGH|LOW)([A-Z]{2,5})-\d{2}[A-Z]{3}\d{2}-T(\d+(\.\d+)?)"
        )
        match = re.search(threshold_pattern, market.market_id)
        if match:
            high_low = match.group(1).lower()
            city_code = match.group(2)
            strike = float(match.group(3))

            q_text = market.question.lower()

            # --- CRITICAL FIX: Robust Direction Detection ---
            is_below = False
            is_above = False

            # Check for explicit symbols and phrases
            if "<" in q_text or "below" in q_text or "less than" in q_text:
                is_below = True
            elif (
                ">" in q_text
                or "above" in q_text
                or "greater than" in q_text
                or "more than" in q_text
            ):
                is_above = True

            # Fallback logic if ambiguous (Kalshi convention: usually T is Above, but check price?)
            # Ideally, we trust the text. If both present (rare), prioritize symbolic < >

            if is_below:
                threshold_type = f"{high_low}_below"
                # If market says "Below 40", it includes 39, usually excludes 40.
                threshold = strike
            else:
                # Default to Above
                threshold_type = f"{high_low}_above"
                threshold = strike

            return {
                "location": KalshiClient._map_city(city_code),
                "threshold_temp": threshold,
                "threshold_type": threshold_type,
                "is_bucket": False,
            }

        return None

    @staticmethod
    def _map_city(code: str) -> str:
        mapping = {
            "NY": "New York",
            "CHI": "Chicago",
            "LAX": "Los Angeles",
            "LA": "Los Angeles",
            "MIA": "Miami",
            "BOS": "Boston",
            "DEN": "Denver",
            "ATL": "Atlanta",
            "PHL": "Philadelphia",
            "PHX": "Phoenix",
            "TATL": "Atlanta",
            "TBOS": "Boston",
        }
        return mapping.get(code, code)
