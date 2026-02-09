"""
Kalshi Edge Detection Engine - Main Entry Point

This is the main execution loop for the edge detection engine.
It continuously:
1. Polls Kalshi markets for weather-related prediction markets
2. Fetches relevant weather data
3. Computes fair probabilities using a simple, explainable model
4. Detects mispricings (edge) when fair_prob diverges from market_prob
5. Emits structured signals when edge exceeds threshold

Run: python -m edge_engine.main
"""

import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from edge_engine.data import KalshiClient, WeatherClient
from edge_engine.models import WeatherProbabilityModel
from edge_engine.signals import SignalEmitter
from edge_engine.utils.config_loader import load_config, get_nested
from edge_engine.utils.logging_setup import setup_logging, get_logger


class EdgeEngine:
    """
    Main edge detection engine.
    
    Orchestrates data fetching, probability estimation, edge detection,
    and signal emission in a continuous polling loop.
    """
    
    def __init__(self, config_path: str | None = None):
        """
        Initialize the edge engine.
        
        Args:
            config_path: Path to config.yaml. Defaults to ./config.yaml
        """
        # Load configuration
        self.config = load_config(config_path)
        
        # Setup logging
        log_level = get_nested(self.config, "logging", "level", default="INFO")
        self.logger = setup_logging(log_level)
        self.logger.info("Initializing Edge Engine...")
        
        # Initialize components
        self.kalshi_client = KalshiClient(self.config)
        self.weather_client = WeatherClient(self.config)
        self.probability_model = WeatherProbabilityModel(
            self.weather_client, 
            self.config
        )
        self.signal_emitter = SignalEmitter(self.config)
        
        # Configuration values
        self.edge_threshold = get_nested(
            self.config, "edge", "threshold", default=0.05
        )
        self.poll_interval = get_nested(
            self.config, "polling", "interval_seconds", default=30
        )
        self.markets_per_cycle = get_nested(
            self.config, "polling", "markets_per_cycle", default=10
        )
        
        # Runtime state
        self._running = False
        self._cycle_count = 0
        
        self.logger.info(
            f"Engine configured: threshold={self.edge_threshold:.1%}, "
            f"poll_interval={self.poll_interval}s"
        )
    
    def run(self) -> None:
        """
        Start the main execution loop.
        
        Runs continuously until interrupted (Ctrl+C).
        """
        self._running = True
        self.logger.info("Edge Engine started. Press Ctrl+C to stop.")
        
        try:
            while self._running:
                self._run_cycle()
                
                if self._running:
                    self.logger.debug(f"Sleeping for {self.poll_interval}s...")
                    time.sleep(self.poll_interval)
                    
        except KeyboardInterrupt:
            self.logger.info("Shutdown signal received")
        finally:
            self._shutdown()
    
    def run_once(self) -> list[dict]:
        """
        Run a single detection cycle.
        
        Useful for testing or one-off runs.
        
        Returns:
            List of signal dictionaries for any edges detected.
        """
        return self._run_cycle()
    
    def _run_cycle(self) -> list[dict]:
        """
        Execute one detection cycle.
        
        Returns:
            List of emitted signal dictionaries.
        """
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        
        self.logger.info(f"--- Cycle {self._cycle_count} starting ---")
        
        # 1. Fetch markets
        markets = self.kalshi_client.get_weather_markets()
        if not markets:
            self.logger.warning("No markets fetched, skipping cycle")
            return []
        
        self.logger.info(f"Fetched {len(markets)} weather markets")
        
        # 2. Evaluate each market for edge
        signals_emitted = []
        edges_found = 0
        
        for market in markets[:self.markets_per_cycle]:
            # Evaluate market
            result = self.probability_model.evaluate_market(market)
            if result is None:
                continue
            
            # Log all evaluations at DEBUG level
            self.logger.debug(
                f"{market.market_id}: "
                f"market={result.market_prob:.1%}, "
                f"fair={result.fair_prob:.1%}, "
                f"edge={result.edge:+.1%}"
            )
            
            # Check if edge exceeds threshold
            if abs(result.edge) >= self.edge_threshold:
                edges_found += 1
                
                # Emit signal
                from edge_engine.signals import Signal
                signal = Signal.from_edge_result(result)
                
                if self.signal_emitter.emit(signal):
                    signals_emitted.append(signal.to_dict())
        
        # Cycle summary
        cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        self.logger.info(
            f"Cycle {self._cycle_count} complete: "
            f"evaluated={len(markets)}, edges={edges_found}, "
            f"signals={len(signals_emitted)}, duration={cycle_duration:.2f}s"
        )
        
        return signals_emitted
    
    def _shutdown(self) -> None:
        """Clean shutdown procedure."""
        self._running = False
        self.logger.info(f"Edge Engine stopped after {self._cycle_count} cycles")
    
    def stop(self) -> None:
        """Signal the engine to stop gracefully."""
        self._running = False


def main():
    """Main entry point."""
    # Handle SIGTERM for graceful container shutdown
    engine = None
    
    def signal_handler(signum, frame):
        if engine:
            engine.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Allow config path override via command line
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    engine = EdgeEngine(config_path)
    engine.run()


if __name__ == "__main__":
    main()
