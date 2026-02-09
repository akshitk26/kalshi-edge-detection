# Kalshi Edge Detection Engine

A Python-based edge detection engine for identifying mispricings in Kalshi prediction markets.

## Overview

This system continuously:
1. **Pulls live Kalshi market data** (weather markets)
2. **Fetches external weather data** (OpenWeatherMap or mock)
3. **Computes fair probabilities** using a simple, explainable model
4. **Detects mispricings** when edge exceeds configurable threshold
5. **Emits structured signals** for downstream consumption

**This is NOT a trading bot.** It is an edge-detection + alerting engine.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with mock data (default)
python -m edge_engine.main

# Run with real APIs (set environment variables first)
export KALSHI_API_KEY="your-key"
export OPENWEATHER_API_KEY="your-key"
python -m edge_engine.main
```

## Architecture

```
edge_engine/
├── main.py                    # Entry point, main loop
├── config.yaml                # Configuration
├── data/
│   ├── kalshi_client.py       # Kalshi market data fetching
│   └── weather_client.py      # Weather forecast fetching
├── models/
│   └── probability_model.py   # Fair probability computation
├── signals/
│   └── signal_emitter.py      # Signal emission (console/HTTP)
└── utils/
    ├── config_loader.py       # YAML config loading
    └── logging_setup.py       # Structured logging
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `KalshiClient` | Fetches market data, parses market parameters |
| `WeatherClient` | Fetches weather forecasts (real API or mock) |
| `WeatherProbabilityModel` | Computes fair probability using normal CDF |
| `SignalEmitter` | Emits signals to console or HTTP endpoint |
| `EdgeEngine` | Orchestrates the detection loop |

## Data Flow

```
┌─────────────────┐     ┌──────────────────┐
│  Kalshi Markets │     │  Weather Forecast │
│  (yes_price)    │     │  (temp ± std)     │
└────────┬────────┘     └────────┬──────────┘
         │                       │
         ▼                       ▼
    ┌────────────────────────────────────┐
    │      WeatherProbabilityModel       │
    │  P(temp > threshold) via erf()     │
    └────────────────┬───────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │ edge = fair │
              │  - market   │
              └──────┬──────┘
                     │
          ┌──────────┴──────────┐
          │                     │
    edge < threshold      edge >= threshold
          │                     │
          ▼                     ▼
       (skip)            ┌─────────────┐
                         │ Emit Signal │
                         └─────────────┘
```

## Edge Calculation

For weather markets:
1. Parse market (e.g., "HIGHNY-26FEB09-T55" → NYC, high > 55°F)
2. Fetch forecast (e.g., high = 52°F ± 3.5°F)
3. Compute: `P(high > 55) = 1 - Φ((55 - 52) / 3.5) ≈ 19.6%`
4. Compare to market: market = 62%, fair = 19.6%
5. Edge = -42.4% → Market significantly overprices YES

## Signal Format

```json
{
  "market_id": "HIGHNY-26FEB09-T55",
  "market_question": "Will the high temperature in NYC be above 55°F on February 9?",
  "market_prob": 0.62,
  "fair_prob": 0.196,
  "edge": -0.424,
  "confidence": 0.85,
  "timestamp": "2026-02-08T15:30:00+00:00",
  "reasoning": "Forecast high: 52.0°F ± 3.5°F | P(high above 55°F) = 19.6% | Market: 62.0% | Market overprices YES by 42.4%",
  "direction": "NO"
}
```

## Configuration

Key settings in `config.yaml`:

```yaml
edge:
  threshold: 0.05  # Minimum edge to trigger (5%)

polling:
  interval_seconds: 30  # Poll frequency

signal:
  mode: "console"  # or "http"
  http_endpoint: "http://localhost:8080/api/signals"
```

## Example Output

```
======================================================================
🎯 EDGE DETECTED
======================================================================
Market:     HIGHNY-26FEB09-T55
Question:   Will the high temperature in NYC be above 55°F on February 9?
Market Prob: 62.0%
Fair Prob:   19.6%
Edge:        -42.4% (NO)
Confidence:  85.0%
Timestamp:   2026-02-08T15:30:00+00:00
----------------------------------------------------------------------
Reasoning:   Forecast high: 52.0°F ± 3.5°F | P(high above 55°F) = 19.6% | Market: 62.0% | Market overprices YES by 42.4%
======================================================================
```

## Extending

### Adding New Data Sources

1. Create a new client in `data/` (e.g., `sports_client.py`)
2. Create a probability model in `models/`
3. Register in `main.py`

### Spring Boot Integration

Set `signal.mode: "http"` and configure `signal.http_endpoint` to POST signals to your Spring Boot service.

## Development

```bash
# Type checking
mypy edge_engine/

# Testing
pytest tests/

# Formatting
black edge_engine/
```

## License

MIT
