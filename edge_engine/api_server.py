"""
Edge Engine API Server

Serves market analysis data as JSON for the frontend UI.

Run: python -m edge_engine.api_server
"""

import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

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


# ─── Portfolio History Reconstruction ────────────────────────────────

HISTORY_CACHE_FILE = Path(__file__).parent / "portfolio_history_cache.json"
_history_cache: list[dict] | None = None
_history_lock = threading.Lock()


def _reconstruct_portfolio_history() -> list[dict]:
    """
    Reconstruct portfolio value timeline from fills + settlements.

    Uses position tracking with the correct Kalshi price model:
    - BUY fills: cash out = count * side_price + fee, position gained
    - SELL fills: realized P&L = (count * opposite_side_price) - cost_basis - fee
      The ``side`` field indicates the order-book side, so closing a NO
      position appears as side=yes,action=sell.  The user receives
      ``no_price`` (the opposite side) per contract in that case.
    - Settlements: realized P&L = revenue - remaining cost basis

    Total value at each point = initial_deposit + cumulative realized P&L.
    Initial deposit is derived from the Model-C cash-flow identity.
    """
    global _history_cache

    with _history_lock:
        if _history_cache is not None:
            return _history_cache

    fills = _kalshi_client.get_fills()
    settlements = _kalshi_client.get_settlements()
    balance_info = _kalshi_client.get_balance()
    current_total = balance_info["total_value"]

    # --- Derive initial deposit using Model C cash-flow identity ---
    total_out = 0
    total_in = 0
    for f in fills:
        side = f.get("side", "")
        action = f.get("action", "")
        count = f.get("count", 0)
        yp = f.get("yes_price", 0)
        np_ = f.get("no_price", 0)
        fee = round(float(f.get("fee_cost", "0")) * 100)
        if action == "buy":
            price = np_ if side == "no" else yp
            total_out += count * price + fee
        else:
            price = np_ if side == "yes" else yp
            total_in += count * price - fee
    for s in settlements:
        total_in += s.get("revenue", 0)

    initial_value = current_total - (total_in - total_out)

    # --- Build event list with position-tracked deltas ---
    events: list[dict] = []

    for f in fills:
        events.append({
            "ts": f.get("created_time") or "",
            "type": "fill",
            "fill": f,
        })

    for s in settlements:
        events.append({
            "ts": s.get("settled_time", ""),
            "type": "settlement",
            "settlement": s,
        })

    if not events:
        return []

    events.sort(key=lambda e: e["ts"])

    from collections import defaultdict
    positions: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_cost": 0})
    running_value = initial_value
    snapshots: list[dict] = []

    first_ts = events[0]["ts"]
    if first_ts:
        try:
            first_dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            snapshots.append({
                "ts": first_dt.replace(second=0, microsecond=0).isoformat(),
                "epoch": int(first_dt.timestamp()) - 1,
                "total_value": initial_value,
                "event": "initial",
            })
        except Exception:
            pass

    for ev in events:
        if ev["type"] == "fill":
            f = ev["fill"]
            side = f.get("side", "")
            action = f.get("action", "")
            count = f.get("count", 0)
            yp = f.get("yes_price", 0)
            np_ = f.get("no_price", 0)
            fee = round(float(f.get("fee_cost", "0")) * 100)
            ticker = f.get("ticker", "")

            if action == "buy":
                buy_price = np_ if side == "no" else yp
                positions[ticker]["count"] += count
                positions[ticker]["total_cost"] += count * buy_price
                delta = -fee
            else:
                received_per = np_ if side == "yes" else yp
                pos = positions[ticker]
                if pos["count"] > 0:
                    avg_cost = pos["total_cost"] / pos["count"]
                    cost_basis = avg_cost * count
                else:
                    cost_basis = 0
                received = count * received_per
                delta = round(received - cost_basis - fee)
                positions[ticker]["count"] -= count
                positions[ticker]["total_cost"] -= round(cost_basis)

        elif ev["type"] == "settlement":
            s = ev["settlement"]
            ticker = s.get("ticker", "")
            revenue = s.get("revenue", 0)
            cost_basis = positions[ticker]["total_cost"]
            delta = revenue - cost_basis
            positions[ticker] = {"count": 0, "total_cost": 0}

        else:
            delta = 0

        running_value += delta

        try:
            dt = datetime.fromisoformat(ev["ts"].replace("Z", "+00:00"))
            epoch = int(dt.timestamp())
        except Exception:
            continue

        snapshots.append({
            "ts": dt.isoformat(),
            "epoch": epoch,
            "total_value": running_value,
            "event": ev["type"],
        })

    snapshots.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "epoch": int(time.time()),
        "total_value": current_total,
        "event": "current",
    })

    with _history_lock:
        _history_cache = snapshots
    try:
        HISTORY_CACHE_FILE.write_text(json.dumps(snapshots))
    except Exception:
        pass

    return snapshots


def _try_load_cached_history() -> list[dict] | None:
    try:
        if HISTORY_CACHE_FILE.exists():
            return json.loads(HISTORY_CACHE_FILE.read_text())
    except Exception:
        pass
    return None


# ─── Portfolio Endpoints ─────────────────────────────────────────────


@app.route("/api/portfolio/status", methods=["GET"])
def portfolio_status():
    """Check if portfolio features are available (API key configured)."""
    configured = _kalshi_client is not None and _kalshi_client.has_auth
    return jsonify({"configured": configured})


@app.route("/api/portfolio/balance", methods=["GET"])
def portfolio_balance():
    """Fetch current balance, portfolio value, and positions."""
    if not _kalshi_client or not _kalshi_client.has_auth:
        return jsonify({"error": "API key not configured"}), 401
    try:
        balance = _kalshi_client.get_balance()
        positions = _kalshi_client.get_positions()
        return jsonify({
            "balance": balance,
            "positions": positions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        _logger.error(f"Portfolio balance error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/portfolio/history", methods=["GET"])
def portfolio_history():
    """Return reconstructed portfolio value timeline from fills/settlements."""
    if not _kalshi_client or not _kalshi_client.has_auth:
        return jsonify({"error": "API key not configured"}), 401
    try:
        refresh = request.args.get("refresh", "").lower() == "true"
        if refresh:
            global _history_cache
            with _history_lock:
                _history_cache = None

        snapshots = _reconstruct_portfolio_history()

        return jsonify({
            "snapshots": snapshots,
            "count": len(snapshots),
        })
    except Exception as e:
        _logger.error(f"Portfolio history error: {e}", exc_info=True)
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

    if _kalshi_client and _kalshi_client.has_auth:
        _logger.info("Portfolio auth detected — portfolio features enabled")
    else:
        _logger.info("No Kalshi API key — portfolio features disabled")

    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
