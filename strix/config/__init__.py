"""Strix Configuration Module.

This module provides configuration management for Strix, including:
- config.json file-based configuration for CLIProxyAPI endpoints
- Environment variable overrides
- Runtime configuration updates
"""

from strix.config.config import (
    Config,
    apply_saved_config,
    save_current_config,
)

from strix.config.config_manager import (
    ConfigManager,
    DashboardConfig,
    StrixConfig,
    TimeframeConfig,
    get_config,
    load_config,
    save_config,
)


__all__ = [
    # Legacy Config class
    "Config",
    "apply_saved_config",
    "save_current_config",
    # New config manager
    "ConfigManager",
    "DashboardConfig",
    "StrixConfig",
    "TimeframeConfig",
    "get_config",
    "load_config",
    "save_config",
]
