"""
Edge Engine API Server

Serves market analysis data as JSON for the frontend UI.

Run: python -m edge_engine.api_server
"""

import sys
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS

from edge_engine.data import KalshiClient, WeatherClient
from edge_engine.models import WeatherProbabilityModel
from edge_engine.hedge import MarketGrouper, HedgeCalculator
from edge_engine.utils.config_loader import load_config
from edge_engine.utils.logging_setup import setup_logging, get_logger

app = Flask(__name__)
CORS(app)

# Global state — initialized once at startup
_config = None
_kalshi_client = None
_weather_client = None
_probability_model = None
_market_grouper = None
_hedge_calculator = None
_logger = None


def _init_clients():
    global _config, _kalshi_client, _weather_client, _probability_model, _market_grouper, _hedge_calculator, _logger
    _config = load_config()
    _logger = setup_logging("INFO")
    _kalshi_client = KalshiClient(_config)
    _weather_client = WeatherClient(_config)
    _probability_model = WeatherProbabilityModel(_weather_client, _config)
    _market_grouper = MarketGrouper()
    _hedge_calculator = HedgeCalculator()


def _market_to_dict(result) -> dict:
    """Convert an EdgeResult to a frontend-friendly dict."""
    market = result.market
    series_ticker = market.market_id.split("-")[0].lower()

    # Determine action
    if abs(result.edge) < 0.05:
        action = "HOLD"
    elif result.edge > 0:
        action = "BUY YES"
    else:
        action = "BUY NO"

    # Extract city from question or ticker
    city = ""
    params = KalshiClient.parse_market_params(market)
    if params:
        city = params.get("location", "")

    # Extract date from ticker (e.g., KXHIGHNY-26FEB14-B46.5 → 26FEB14)
    ticker_parts = market.market_id.split("-")
    date_str = ticker_parts[1] if len(ticker_parts) >= 2 else ""

    return {
        "ticker": market.market_id,
        "question": market.question,
        "marketPrice": round(market.market_prob * 100, 1),
        "fairProbability": round(result.fair_prob * 100, 1),
        "edge": round(result.edge * 100, 1),
        "action": action,
        "confidence": round(result.confidence * 100, 1),
        "volume": market.volume,
        "hasLiquidity": market.has_liquidity,
        "reasoning": result.reasoning,
        "city": city,
        "date": date_str,
        "resolutionUrl": f"https://kalshi.com/markets/{series_ticker}",
        "closeTime": market.close_time.isoformat(),
    }


@app.route("/api/markets", methods=["GET"])
def get_markets():
    """
    Fetch and analyze all open weather markets.

    Query params:
        series: comma-separated series tickers (optional, defaults to all)

    Returns JSON:
        {
            "markets": [...],
            "meta": { "timestamp": "...", "count": N, "priceSource": "..." }
        }
    """
    try:
        series_param = request.args.get("series", "")

        if series_param:
            series_list = [s.strip().upper() for s in series_param.split(",")]
        else:
            series_list = None  # use defaults

        # Fetch markets
        if series_list:
            markets = []
            for s in series_list:
                from edge_engine.analyze_market import fetch_series_markets

                markets.extend(fetch_series_markets(_kalshi_client, s))
        else:
            markets = _kalshi_client.get_weather_markets()

        # Evaluate each market
        results = []
        for market in markets:
            result = _probability_model.evaluate_market(market)
            if result is not None:
                results.append(_market_to_dict(result))

        # Sort by absolute edge descending
        results.sort(key=lambda r: abs(r["edge"]), reverse=True)

        return jsonify(
            {
                "markets": results,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "count": len(results),
                    "priceSource": _kalshi_client.price_source,
                },
            }
        )

    except Exception as e:
        _logger.error(f"API error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/markets/<ticker>", methods=["GET"])
def get_market(ticker: str):
    """Fetch and analyze a single market by ticker."""
    try:
        from edge_engine.analyze_market import fetch_single_market

        market = fetch_single_market(_kalshi_client, ticker.upper())
        if not market:
            return jsonify({"error": f"Market {ticker} not found"}), 404

        result = _probability_model.evaluate_market(market)
        if result is None:
            return jsonify({"error": f"Could not analyze {ticker}"}), 422

        return jsonify({"market": _market_to_dict(result)})

    except Exception as e:
        _logger.error(f"API error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/lookup", methods=["GET"])
def lookup_market():
    """
    Look up and analyze markets by Kalshi URL or ticker.

    Query params:
        q: Kalshi URL, market ticker, or series ticker

    Returns same structure as /api/markets.
    """
    try:
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"error": "Missing ?q= parameter"}), 400

        from edge_engine.analyze_market import (
            parse_kalshi_url,
            fetch_series_markets,
            fetch_single_market,
        )

        series_ticker, market_ticker = parse_kalshi_url(q)

        if not series_ticker:
            return jsonify({"error": f"Could not parse: {q}"}), 400

        # Fetch markets
        if (
            market_ticker
            and "-" in market_ticker
            and len(market_ticker.split("-")) >= 2
        ):
            markets = fetch_series_markets(_kalshi_client, series_ticker)
            markets = [
                m
                for m in markets
                if m.market_id.upper().startswith(market_ticker.upper())
            ]
            if not markets:
                market = fetch_single_market(_kalshi_client, market_ticker)
                markets = [market] if market else []
        else:
            markets = fetch_series_markets(_kalshi_client, series_ticker)

        if not markets:
            return jsonify({"error": f"No markets found for {q}"}), 404

        results = []
        for market in markets:
            result = _probability_model.evaluate_market(market)
            if result is not None:
                results.append(_market_to_dict(result))

        results.sort(key=lambda r: abs(r["edge"]), reverse=True)

        return jsonify(
            {
                "markets": results,
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "count": len(results),
                    "priceSource": _kalshi_client.price_source,
                    "query": q,
                },
            }
        )

    except Exception as e:
        _logger.error(f"Lookup error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ─── Hedge Group Endpoints ───────────────────────────────────────────


@app.route("/api/hedge-groups", methods=["GET"])
def get_hedge_groups():
    """
    Fetch all current hedge groups (markets grouped by city+date).

    Query params:
        series: comma-separated series tickers (optional)
    """
    try:
        series_param = request.args.get("series", "")

        if series_param:
            series_list = [s.strip().upper() for s in series_param.split(",")]
            markets = []
            for s in series_list:
                from edge_engine.analyze_market import fetch_series_markets

                markets.extend(fetch_series_markets(_kalshi_client, s))
        else:
            markets = _kalshi_client.get_weather_markets()

        groups = _market_grouper.group_markets(markets)

        return jsonify(
            {
                "groups": [g.to_dict() for g in groups],
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "count": len(groups),
                    "totalMarkets": len(markets),
                    "priceSource": _kalshi_client.price_source,
                },
            }
        )

    except Exception as e:
        _logger.error(f"Hedge groups error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/hedge-groups/<group_id>/calculate", methods=["GET"])
def calculate_hedge(group_id: str):
    """
    Calculate optimal allocation for a hedge group.

    Query params:
        budget: budget in dollars (required)
        fee: fee per contract in dollars (optional, default 0.011)
        selected: comma-separated tickers to include (optional, default all)
        exitThreshold: exit threshold as YES probability (optional, 0.0-1.0, default from config)
    """
    try:
        budget_str = request.args.get("budget")
        if not budget_str:
            return jsonify({"error": "Missing ?budget= parameter"}), 400

        try:
            budget = float(budget_str)
        except ValueError:
            return jsonify({"error": "Invalid budget: {budget_str}"}), 400

        if budget <= 0:
            return jsonify({"error": "Budget must be positive"}), 400

        fee = float(request.args.get("fee", "0.011"))

        exit_threshold_str = request.args.get("exitThreshold")
        exit_threshold = None
        if exit_threshold_str:
            try:
                exit_threshold = float(exit_threshold_str)
                if not (0 < exit_threshold < 1):
                    return (
                        jsonify({"error": "exitThreshold must be between 0 and 1"}),
                        400,
                    )
            except ValueError:
                return jsonify({"error": "Invalid exitThreshold"}), 400

        # Build config with exit threshold override if provided
        config = dict(_config) if _config else {}
        if exit_threshold is not None:
            config.setdefault("hedge", {})["exit_threshold"] = exit_threshold

        selected_param = request.args.get("selected", "")
        selected_tickers = (
            [s.strip().upper() for s in selected_param.split(",") if s.strip()]
            if selected_param
            else None
        )

        # Fetch markets and find the matching group
        markets = _kalshi_client.get_weather_markets()
        groups = _market_grouper.group_markets(markets)

        target_group = None
        for g in groups:
            if g.group_id.upper() == group_id.upper():
                target_group = g
                break

        if not target_group:
            return jsonify({"error": f"Group {group_id} not found"}), 404

        result = _hedge_calculator.calculate(
            target_group, budget, fee, selected_tickers, config
        )

        return jsonify(
            {
                "allocation": result.to_dict(),
                "group": target_group.to_dict(),
            }
        )

    except Exception as e:
        _logger.error(f"Hedge calculate error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify(
        {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    )


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    _init_clients()
    _logger.info(f"Starting API server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
