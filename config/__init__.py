"""
Filefy Configuration Package.

This package provides centralized configuration management for the Filefy application.
It handles loading, validation, and access to all configuration files.

Usage:
    from config import config_manager, get_settings, get_security, get_details

    # Get the full config manager
    config = config_manager

    # Or use convenience functions
    settings = get_settings()
    security = get_security()
    details = get_details()
"""

from .config_manager import (
    ConfigManager,
    ConfigLoader,
    ConfigurationError,
    SettingsConfig,
    SecurityConfig,
    DetailsConfig,
    config_manager,
    get_config,
    get_settings,
    get_security,
    get_details,
    reload_config,
)

__all__ = [
    # Classes
    "ConfigManager",
    "ConfigLoader",
    "ConfigurationError",
    "SettingsConfig",
    "SecurityConfig",
    "DetailsConfig",
    # Singleton instance
    "config_manager",
    # Convenience functions
    "get_config",
    "get_settings",
    "get_security",
    "get_details",
    "reload_config",
]

