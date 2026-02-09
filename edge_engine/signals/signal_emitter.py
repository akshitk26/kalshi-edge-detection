"""
Signal Emitter

Handles emission of edge detection signals.
Supports console output and HTTP POST for Spring Boot integration.

Signals are immutable data objects representing actionable edge detection events.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import requests

from edge_engine.models.probability_model import EdgeResult
from edge_engine.utils.logging_setup import get_logger

logger = get_logger("edge_engine.signals")


@dataclass(frozen=True)
class Signal:
    """
    Immutable signal object representing a detected edge.
    
    This is the core output of the edge detection engine.
    Designed for easy serialization and integration with downstream systems.
    """
    market_id: str
    market_question: str
    market_prob: float
    fair_prob: float
    edge: float
    confidence: float
    timestamp: str  # ISO-8601 format
    
    # Additional context (optional, for debugging/analysis)
    reasoning: str = ""
    direction: str = ""  # "YES" or "NO" - which side has edge
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_edge_result(cls, result: EdgeResult) -> "Signal":
        """Create a Signal from an EdgeResult."""
        return cls(
            market_id=result.market.market_id,
            market_question=result.market.question,
            market_prob=round(result.market_prob, 4),
            fair_prob=round(result.fair_prob, 4),
            edge=round(result.edge, 4),
            confidence=round(result.confidence, 4),
            timestamp=datetime.now(timezone.utc).isoformat(),
            reasoning=result.reasoning,
            direction=result.direction
        )


class SignalEmitter:
    """
    Handles signal emission to various outputs.
    
    Modes:
    - "console": Print signals to stdout (default)
    - "http": POST signals to configured endpoint
    """
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize the signal emitter.
        
        Args:
            config: Configuration dictionary with signal settings.
        """
        signal_config = config.get("signal", {})
        self.mode = signal_config.get("mode", "console")
        self.http_endpoint = signal_config.get("http_endpoint", "")
        
        # Track emitted signals for deduplication (in-memory for now)
        self._recent_signals: dict[str, datetime] = {}
        self._dedup_window_seconds = 300  # 5 minutes
        
        # HTTP session for connection pooling
        if self.mode == "http":
            self._session = requests.Session()
            self._session.headers.update({"Content-Type": "application/json"})
        
        logger.info(f"Signal emitter initialized in '{self.mode}' mode")
    
    def emit(self, signal: Signal) -> bool:
        """
            Emit a signal to the configur                           `````                          ```````ed output.
            
        Args:
            signal: The Signal to emit.
        
        Returns:
            True if emission succeeded, False otherwise.
        """
        # Deduplication check
        if self._is_duplicate(signal):
            logger.debug(f"Skipping duplicate signal for {signal.market_id}")
            return False
        
        # Emit based on mode
        success = False
        if self.mode == "console":
            success = self._emit_console(signal)
        elif self.mode == "http":
            success = self._emit_http(signal)
        else:
            logger.error(f"Unknown signal mode: {self.mode}")
            return False
        
        if success:
            self._record_signal(signal)
        
        return success
    
    def emit_from_edge_result(self, result: EdgeResult) -> bool:
        """
        Convenience method to emit directly from EdgeResult.
        
        Args:
            result: The EdgeResult to convert and emit.
        
        Returns:
            True if emission succeeded, False otherwise.
        """
        signal = Signal.from_edge_result(result)
        return self.emit(signal)
    
    def _emit_console(self, signal: Signal) -> bool:
        """Print signal to console in a structured format."""
        try:
            # Formatted console output
            print("\n" + "=" * 70)
            print("🎯 EDGE DETECTED")
            print("=" * 70)
            print(f"Market:     {signal.market_id}")
            print(f"Question:   {signal.market_question}")
            print(f"Market Prob: {signal.market_prob:.1%}")
            print(f"Fair Prob:   {signal.fair_prob:.1%}")
            print(f"Edge:        {signal.edge:+.1%} ({signal.direction})")
            print(f"Confidence:  {signal.confidence:.1%}")
            print(f"Timestamp:   {signal.timestamp}")
            print("-" * 70)
            print(f"Reasoning:   {signal.reasoning}")
            print("=" * 70 + "\n")
            
            # Also log for file capture
            logger.info(
                f"SIGNAL: {signal.market_id} | "
                f"edge={signal.edge:+.1%} | "
                f"confidence={signal.confidence:.1%}"
            )
            
            return True
        except Exception as e:
            logger.error(f"Failed to emit console signal: {e}")
            return False
    
    def _emit_http(self, signal: Signal) -> bool:
        """POST signal to HTTP endpoint."""
        if not self.http_endpoint:
            logger.error("HTTP endpoint not configured")
            return False
        
        try:
            response = self._session.post(
                self.http_endpoint,
                data=signal.to_json(),
                timeout=10
            )
            response.raise_for_status()
            
            logger.info(
                f"Signal posted to {self.http_endpoint}: "
                f"{signal.market_id} (status={response.status_code})"
            )
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to POST signal to {self.http_endpoint}: {e}")
            # Fall back to console output
            logger.info("Falling back to console output")
            return self._emit_console(signal)
    
    def _is_duplicate(self, signal: Signal) -> bool:
        """Check if we've recently emitted a signal for this market."""
        last_emit = self._recent_signals.get(signal.market_id)
        if last_emit is None:
            return False
        
        now = datetime.now(timezone.utc)
        age = (now - last_emit).total_seconds()
        return age < self._dedup_window_seconds
    
    def _record_signal(self, signal: Signal) -> None:
        """Record signal emission for deduplication."""
        self._recent_signals[signal.market_id] = datetime.now(timezone.utc)
        
        # Cleanup old entries
        self._cleanup_old_signals()
    
    def _cleanup_old_signals(self) -> None:
        """Remove signals older than dedup window."""
        now = datetime.now(timezone.utc)
        cutoff_seconds = self._dedup_window_seconds * 2  # Keep some buffer
        
        to_remove = [
            market_id for market_id, timestamp in self._recent_signals.items()
            if (now - timestamp).total_seconds() > cutoff_seconds
        ]
        
        for market_id in to_remove:
            del self._recent_signals[market_id]
