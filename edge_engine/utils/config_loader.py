"""Configuration loader utility."""

import os
from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file. Defaults to config.yaml in edge_engine root.
    
    Returns:
        Configuration dictionary.
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Override with environment variables where applicable
    if os.getenv("KALSHI_API_KEY"):
        config.setdefault("kalshi", {})["api_key"] = os.getenv("KALSHI_API_KEY")
    
    if os.getenv("OPENWEATHER_API_KEY"):
        config.setdefault("weather", {})["api_key"] = os.getenv("OPENWEATHER_API_KEY")
    
    return config


def get_nested(config: dict, *keys, default=None) -> Any:
    """
    Safely get nested config values.
    
    Usage: get_nested(config, "edge", "threshold", default=0.05)
    """
    value = config
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return default
        if value is None:
            return default
    return value
