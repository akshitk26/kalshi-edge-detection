#!/usr/bin/env python3
"""
Analyze a specific Kalshi market by URL or ticker.

Usage:
    python3 -m edge_engine.analyze_market "https://kalshi.com/markets/kxhightatl/atlanta-max-temperature/kxhightatl-26feb09"
    python3 -m edge_engine.analyze_market KXHIGHTATL-26FEB09-T40
    python3 -m edge_engine.analyze_market kxhighny  # Analyze all markets in series
"""

import re
import sys
from datetime import datetime, timezone

from edge_engine.data import KalshiClient, WeatherClient
from edge_engine.models import WeatherProbabilityModel
from edge_engine.utils.config_loader import load_config
from edge_engine.utils.logging_setup import setup_logging


def parse_kalshi_url(url: str) -> tuple[str | None, str | None]:
    """
    Parse a Kalshi URL to extract series ticker and market ticker.
    
    Examples:
        https://kalshi.com/markets/kxhightatl/atlanta-max-temperature/kxhightatl-26feb09
        -> series: KXHIGHTATL, market: KXHIGHTATL-26FEB09
        
        https://kalshi.com/markets/kxhighny
        -> series: KXHIGHNY, market: None (all markets in series)
    
    Returns:
        (series_ticker, market_ticker) - market_ticker may be None for series-level URLs
    """
    # Remove trailing slashes
    url = url.rstrip("/")
    
    # Pattern 1: Full market URL
    # https://kalshi.com/markets/kxhightatl/atlanta-max-temperature/kxhightatl-26feb09
    full_pattern = r"kalshi\.com/markets/([a-zA-Z0-9]+)/[^/]+/([a-zA-Z0-9-]+)$"
    match = re.search(full_pattern, url)
    if match:
        series = match.group(1).upper()
        market = match.group(2).upper()
        return series, market
    
    # Pattern 2: Series URL
    # https://kalshi.com/markets/kxhighny
    series_pattern = r"kalshi\.com/markets/([a-zA-Z0-9]+)$"
    match = re.search(series_pattern, url)
    if match:
        series = match.group(1).upper()
        return series, None
    
    # Pattern 3: Direct ticker (not a URL)
    # KXHIGHTATL-26FEB09 or KXHIGHTATL-26FEB09-T40
    if not url.startswith("http"):
        ticker = url.upper()
        # Extract series from ticker
        if "-" in ticker:
            series = ticker.split("-")[0]
        else:
            series = ticker
        return series, ticker if "-" in ticker else None
    
    return None, None


def fetch_series_markets(client: KalshiClient, series_ticker: str) -> list:
    """Fetch all markets for a series."""
    try:
        response = client._session.get(
            f"{client.base_url}/markets",
            params={"series_ticker": series_ticker, "status": "open", "limit": 50}
        )
        response.raise_for_status()
        data = response.json()
        
        from edge_engine.data.kalshi_client import KalshiMarket
        markets = []
        for market_data in data.get("markets", []):
            try:
                markets.append(KalshiMarket.from_api_response(market_data))
            except Exception:
                pass
        return markets
    except Exception as e:
        print(f"Error fetching series {series_ticker}: {e}")
        return []


def fetch_single_market(client: KalshiClient, market_ticker: str):
    """Fetch a single market by ticker."""
    try:
        response = client._session.get(f"{client.base_url}/markets/{market_ticker}")
        response.raise_for_status()
        data = response.json()
        
        from edge_engine.data.kalshi_client import KalshiMarket
        return KalshiMarket.from_api_response(data["market"])
    except Exception as e:
        print(f"Error fetching market {market_ticker}: {e}")
        return None


def analyze_market(market, weather_client: WeatherClient, probability_model: WeatherProbabilityModel):
    """Analyze a single market and print results."""
    result = probability_model.evaluate_market(market)
    
    if result is None:
        print(f"\n⚠️  Could not analyze market: {market.market_id}")
        print(f"   Question: {market.question}")
        print(f"   (Possibly unsupported city or format)")
        return None
    
    # Determine action
    if result.edge > 0:
        action = "BUY YES"
        action_color = "\033[92m"  # Green
    else:
        action = "BUY NO"
        action_color = "\033[91m"  # Red
    reset = "\033[0m"
    
    # Liquidity warning
    liq_status = "✓ Active" if getattr(market, 'has_liquidity', True) else "⚠️  LOW/STALE"
    
    # Print detailed analysis
    print("\n" + "=" * 70)
    print(f"📊 MARKET ANALYSIS: {market.market_id}")
    print("=" * 70)
    print(f"Question:    {market.question}")
    print(f"Link:        https://kalshi.com/markets/{market.market_id.split('-')[0].lower()}")
    print("-" * 70)
    print(f"Market Prob: {result.market_prob:>6.1%}")
    print(f"Fair Prob:   {result.fair_prob:>6.1%}")
    print(f"Edge:        {result.edge:>+6.1%}")
    print(f"Confidence:  {result.confidence:>6.1%}")
    print("-" * 70)
    print(f"Volume:      {getattr(market, 'volume', 'N/A'):,}")
    print(f"Liquidity:   {liq_status}")
    print("-" * 70)
    print(f"Action:      {action_color}{action}{reset}" if abs(result.edge) >= 0.05 else f"Action:      HOLD (edge < 5%)")
    print(f"Reasoning:   {result.reasoning}")
    print("=" * 70)
    
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m edge_engine.analyze_market <URL_OR_TICKER>")
        print()
        print("Examples:")
        print("  python3 -m edge_engine.analyze_market 'https://kalshi.com/markets/kxhightatl/atlanta-max-temperature/kxhightatl-26feb09'")
        print("  python3 -m edge_engine.analyze_market KXHIGHTATL-26FEB09-T40")
        print("  python3 -m edge_engine.analyze_market kxhighny")
        sys.exit(1)
    
    input_arg = sys.argv[1]
    
    # Parse input
    series_ticker, market_ticker = parse_kalshi_url(input_arg)
    
    if not series_ticker:
        print(f"❌ Could not parse input: {input_arg}")
        print("   Expected a Kalshi URL or market ticker")
        sys.exit(1)
    
    print(f"\n🔍 Analyzing: {series_ticker}" + (f" / {market_ticker}" if market_ticker else " (all markets)"))
    
    # Initialize clients
    setup_logging("WARNING")  # Suppress info logs
    config = load_config()
    
    kalshi_client = KalshiClient(config)
    weather_client = WeatherClient(config)
    probability_model = WeatherProbabilityModel(weather_client, config)
    
    # Fetch markets
    if market_ticker and "-" in market_ticker and len(market_ticker.split("-")) >= 2:
        # Specific market ticker - need to find exact match in series
        markets = fetch_series_markets(kalshi_client, series_ticker)
        # Filter to matching markets
        markets = [m for m in markets if m.market_id.upper().startswith(market_ticker.upper())]
        if not markets:
            # Try fetching single market directly
            market = fetch_single_market(kalshi_client, market_ticker)
            markets = [market] if market else []
    else:
        # Series - get all markets
        markets = fetch_series_markets(kalshi_client, series_ticker)
    
    if not markets:
        print(f"❌ No markets found for {series_ticker}")
        sys.exit(1)
    
    print(f"📈 Found {len(markets)} market(s)")
    
    # Analyze each market
    results = []
    for market in markets:
        result = analyze_market(market, weather_client, probability_model)
        if result:
            results.append(result)
    
    # Print summary if multiple markets
    if len(results) > 1:
        print("\n" + "=" * 70)
        print("📊 SUMMARY TABLE")
        print("=" * 70)
        print(f"{'Market':<30} | {'Mkt':>5} | {'Fair':>5} | {'Edge':>7} | {'Action':<8}")
        print("-" * 70)
        
        # Sort by absolute edge
        results.sort(key=lambda r: abs(r.edge), reverse=True)
        
        for r in results:
            action = "BUY YES" if r.edge > 0 else "BUY NO"
            if abs(r.edge) < 0.05:
                action = "HOLD"
            market_id = r.market.market_id[:29]
            print(f"{market_id:<30} | {r.market_prob:>4.0%} | {r.fair_prob:>4.0%} | {r.edge:>+6.1%} | {action:<8}")
        
        print("=" * 70)
        
        # Best opportunity
        best = results[0]
        if abs(best.edge) >= 0.05:
            action = "BUY YES" if best.edge > 0 else "BUY NO"
            print(f"\n🎯 Best opportunity: {best.market.market_id}")
            print(f"   Edge: {best.edge:+.1%} → {action}")


if __name__ == "__main__":
    main()
