#!/usr/bin/env python3
"""
Configuration Manager for Filefy Application.

This module provides a centralized configuration management system that handles
multiple JSON configuration files including settings, security, details, and build configs.
It implements the Singleton pattern for thread-safe configuration access.

Usage:
    from filefy.config import config_manager

    # Get specific configurations
    settings = config_manager.get_settings()
    security = config_manager.get_security()
    details = config_manager.get_details()

    # Get specific values
    port = config_manager.get_setting("network.port", default=5000)

    # Update settings
    config_manager.set_setting("network.port", 8080)
"""

import json
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from threading import Lock
from copy import deepcopy

# Configure logging
logger = logging.getLogger(__name__)

# Directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(__file__).resolve().parent


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class ConfigLoader:
    """Handles loading and saving of individual JSON configuration files."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def load(self, filename: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load a JSON configuration file.

        Args:
            filename: Name of the JSON file to load
            use_cache: Whether to use cached data if available

        Returns:
            Dictionary containing the configuration data
        """
        with self._lock:
            if use_cache and filename in self._cache:
                return deepcopy(self._cache[filename])

            filepath = self.config_dir / filename

            if not filepath.exists():
                logger.warning(f"Configuration file not found: {filepath}")
                return {}

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cache[filename] = data
                    return deepcopy(data)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {filename}: {e}")
                raise ConfigurationError(f"Invalid JSON in {filename}: {e}")
            except IOError as e:
                logger.error(f"Error reading {filename}: {e}")
                raise ConfigurationError(f"Error reading {filename}: {e}")

    def save(self, filename: str, data: Dict[str, Any]) -> bool:
        """
        Save configuration data to a JSON file.

        Args:
            filename: Name of the JSON file to save
            data: Dictionary containing the configuration data

        Returns:
            True if save was successful, False otherwise
        """
        with self._lock:
            filepath = self.config_dir / filename

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self._cache[filename] = deepcopy(data)
                logger.info(f"Configuration saved: {filename}")
                return True
            except IOError as e:
                logger.error(f"Error saving {filename}: {e}")
                return False

    def clear_cache(self, filename: Optional[str] = None) -> None:
        """Clear the configuration cache."""
        with self._lock:
            if filename:
                self._cache.pop(filename, None)
            else:
                self._cache.clear()


@dataclass
class SettingsConfig:
    """Data class for application settings."""
    host: str = "0.0.0.0"
    port: int = 5000
    root_directory: str = "."
    log_level: str = "INFO"
    log_path: str = "logs/app.log"
    log_format: str = "%(asctime)s [%(levelname)s] : %(message)s"
    read_permission: bool = True
    write_permission: bool = True
    delete_permission: bool = False
    max_upload_size: int = 10 * 1024 * 1024 * 1024  # 10GB
    allowed_extensions: List[str] = field(default_factory=lambda: ["*"])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SettingsConfig":
        """Create SettingsConfig from dictionary."""
        settings = data.get("settings", data)
        network = settings.get("network", {})
        file_manager = settings.get("fileManager", {})
        logging_config = settings.get("logging", {})
        permissions = settings.get("permissions", {})

        # Build log path from array if needed
        log_path_data = logging_config.get("path", "logs/app.log")
        if isinstance(log_path_data, list):
            log_path = str(Path(*log_path_data))
        else:
            log_path = log_path_data

        return cls(
            host=network.get("host", "0.0.0.0"),
            port=network.get("port", 5000),
            root_directory=file_manager.get("rootDirectory", "."),
            log_level=logging_config.get("level", "INFO"),
            log_path=log_path,
            log_format=logging_config.get("format", "%(asctime)s [%(levelname)s] : %(message)s"),
            read_permission=permissions.get("read", True),
            write_permission=permissions.get("write", True),
            delete_permission=permissions.get("delete", False),
            max_upload_size=file_manager.get("maxUploadSize", 10 * 1024 * 1024 * 1024),
            allowed_extensions=file_manager.get("allowedExtensions", ["*"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert SettingsConfig to dictionary."""
        return {
            "settings": {
                "network": {
                    "host": self.host,
                    "port": self.port,
                },
                "fileManager": {
                    "rootDirectory": self.root_directory,
                    "maxUploadSize": self.max_upload_size,
                    "allowedExtensions": self.allowed_extensions,
                },
                "logging": {
                    "level": self.log_level,
                    "path": self.log_path,
                    "format": self.log_format,
                },
                "permissions": {
                    "read": self.read_permission,
                    "write": self.write_permission,
                    "delete": self.delete_permission,
                },
            }
        }


@dataclass
class SecurityConfig:
    """Data class for security settings."""
    jwt_secret: str = ""
    jwt_expires_in: str = "1h"
    bcrypt_salt_rounds: int = 10
    cors_origin: str = "*"
    cors_methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])
    rate_limit_window_ms: int = 900000  # 15 minutes
    rate_limit_max: int = 100
    admin_username: str = "admin"
    admin_password: str = ""
    enable_authentication: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityConfig":
        """Create SecurityConfig from dictionary."""
        security = data.get("security", data)
        jwt = security.get("jwt", {})
        bcrypt = security.get("bcrypt", {})
        cors = security.get("cors", {})
        rate_limit = security.get("rateLimit", {})
        admin = security.get("administrator", {})

        # Calculate rate limit window from array if needed
        window_data = rate_limit.get("windowMs", 900000)
        if isinstance(window_data, list) and len(window_data) >= 3:
            window_ms = window_data[0] * window_data[1] * window_data[2]
        else:
            window_ms = window_data

        return cls(
            jwt_secret=jwt.get("secret", ""),
            jwt_expires_in=jwt.get("expiresIn", "1h"),
            bcrypt_salt_rounds=bcrypt.get("saltRounds", 10),
            cors_origin=cors.get("origin", "*"),
            cors_methods=cors.get("methods", ["GET", "POST", "PUT", "DELETE"]),
            rate_limit_window_ms=window_ms,
            rate_limit_max=rate_limit.get("max", 100),
            admin_username=admin.get("username", "admin"),
            admin_password=admin.get("password", ""),
            enable_authentication=security.get("enableAuthentication", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert SecurityConfig to dictionary."""
        return {
            "security": {
                "enableAuthentication": self.enable_authentication,
                "jwt": {
                    "secret": self.jwt_secret,
                    "expiresIn": self.jwt_expires_in,
                },
                "bcrypt": {
                    "saltRounds": self.bcrypt_salt_rounds,
                },
                "cors": {
                    "origin": self.cors_origin,
                    "methods": self.cors_methods,
                    "preflightContinue": False,
                    "optionsSuccessStatus": 204,
                },
                "rateLimit": {
                    "windowMs": self.rate_limit_window_ms,
                    "max": self.rate_limit_max,
                },
                "administrator": {
                    "username": self.admin_username,
                    "password": self.admin_password,
                },
            }
        }


@dataclass
class DetailsConfig:
    """Data class for application details/metadata."""
    app_name: str = "Filefy"
    version: str = "1.0.0"
    programmer: str = ""
    email: str = ""
    license: str = "MIT"
    description: str = ""
    repository: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetailsConfig":
        """Create DetailsConfig from dictionary."""
        return cls(
            app_name=data.get("appName", "Filefy"),
            version=data.get("version", "1.0.0"),
            programmer=data.get("programmer", ""),
            email=data.get("email", ""),
            license=data.get("license", "MIT"),
            description=data.get("description", ""),
            repository=data.get("repository", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert DetailsConfig to dictionary."""
        return {
            "appName": self.app_name,
            "version": self.version,
            "programmer": self.programmer,
            "email": self.email,
            "license": self.license,
            "description": self.description,
            "repository": self.repository,
        }


class ConfigManager:
    """
    Central configuration manager that handles all application configurations.
    Implements the Singleton pattern for thread-safe access.
    """

    _instance: Optional["ConfigManager"] = None
    _lock: Lock = Lock()

    # Configuration file names
    CONFIG_FILE = "config.json"
    SETTINGS_FILE = "settings.json"
    SECURITY_FILE = "security.json"
    DETAILS_FILE = "details.json"
    BUILD_FILE = "build.json"

    def __new__(cls, config_dir: Optional[Path] = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config_dir: Optional[Path] = None):
        if self._initialized:
            return

        self.config_dir = config_dir or CONFIG_DIR
        self.loader = ConfigLoader(self.config_dir)

        # Load all configurations
        self._settings: Optional[SettingsConfig] = None
        self._security: Optional[SecurityConfig] = None
        self._details: Optional[DetailsConfig] = None
        self._build: Optional[Dict[str, Any]] = None

        self._load_all()
        self._initialized = True
        logger.info(f"ConfigManager initialized with config directory: {self.config_dir}")

    def _load_all(self) -> None:
        """Load all configuration files."""
        try:
            # Load settings
            settings_data = self.loader.load(self.SETTINGS_FILE)
            self._settings = SettingsConfig.from_dict(settings_data)

            # Load security
            security_data = self.loader.load(self.SECURITY_FILE)
            self._security = SecurityConfig.from_dict(security_data)

            # Load details
            details_data = self.loader.load(self.DETAILS_FILE)
            self._details = DetailsConfig.from_dict(details_data)

            # Load build info
            self._build = self.loader.load(self.BUILD_FILE)

        except ConfigurationError as e:
            logger.error(f"Error loading configurations: {e}")
            # Initialize with defaults
            self._settings = SettingsConfig()
            self._security = SecurityConfig()
            self._details = DetailsConfig()
            self._build = {}

    def reload(self) -> None:
        """Reload all configurations from files."""
        self.loader.clear_cache()
        self._load_all()
        logger.info("All configurations reloaded")

    # -------------------------------------------------------------------------
    # Settings Access
    # -------------------------------------------------------------------------

    @property
    def settings(self) -> SettingsConfig:
        """Get settings configuration."""
        return self._settings

    def get_settings(self) -> SettingsConfig:
        """Get settings configuration."""
        return self._settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a specific setting value using dot notation.

        Args:
            key: Setting key in dot notation (e.g., "network.port")
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        parts = key.split(".")
        obj = self._settings

        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return default
        return obj

    def set_setting(self, key: str, value: Any) -> bool:
        """
        Set a specific setting value and save.

        Args:
            key: Setting key (attribute name)
            value: Value to set

        Returns:
            True if successful
        """
        if hasattr(self._settings, key):
            setattr(self._settings, key, value)
            return self.save_settings()
        return False

    def save_settings(self) -> bool:
        """Save current settings to file."""
        return self.loader.save(self.SETTINGS_FILE, self._settings.to_dict())

    # -------------------------------------------------------------------------
    # Security Access
    # -------------------------------------------------------------------------

    @property
    def security(self) -> SecurityConfig:
        """Get security configuration."""
        return self._security

    def get_security(self) -> SecurityConfig:
        """Get security configuration."""
        return self._security

    def save_security(self) -> bool:
        """Save current security settings to file."""
        return self.loader.save(self.SECURITY_FILE, self._security.to_dict())

    # -------------------------------------------------------------------------
    # Details Access
    # -------------------------------------------------------------------------

    @property
    def details(self) -> DetailsConfig:
        """Get application details configuration."""
        return self._details

    def get_details(self) -> DetailsConfig:
        """Get application details configuration."""
        return self._details

    def save_details(self) -> bool:
        """Save current details to file."""
        return self.loader.save(self.DETAILS_FILE, self._details.to_dict())

    # -------------------------------------------------------------------------
    # Build Info Access
    # -------------------------------------------------------------------------

    @property
    def build(self) -> Dict[str, Any]:
        """Get build configuration."""
        return self._build or {}

    def get_build(self) -> Dict[str, Any]:
        """Get build configuration."""
        return self._build or {}

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_flask_config(self) -> Dict[str, Any]:
        """
        Get configuration dictionary suitable for Flask app.config.

        Returns:
            Dictionary with Flask configuration keys
        """
        return {
            "SECRET_KEY": self._security.jwt_secret or os.urandom(24).hex(),
            "MAX_CONTENT_LENGTH": self._settings.max_upload_size,
            "HOST": self._settings.host,
            "PORT": self._settings.port,
            "DEBUG": self._settings.log_level.upper() == "DEBUG",
        }

    def get_cors_config(self) -> Dict[str, Any]:
        """Get CORS configuration for Flask-CORS."""
        return {
            "origins": self._security.cors_origin,
            "methods": self._security.cors_methods,
            "supports_credentials": True,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Export all configurations as a dictionary."""
        return {
            "settings": self._settings.to_dict(),
            "security": self._security.to_dict(),
            "details": self._details.to_dict(),
            "build": self._build,
        }

    def validate(self) -> List[str]:
        """
        Validate all configurations and return list of issues.

        Returns:
            List of validation error messages (empty if valid)
        """
        issues = []

        # Validate settings
        if self._settings.port < 1 or self._settings.port > 65535:
            issues.append("Invalid port number (must be 1-65535)")

        if not self._settings.host:
            issues.append("Host cannot be empty")

        # Validate security
        if self._security.enable_authentication:
            if not self._security.admin_password:
                issues.append("Admin password is required when authentication is enabled")
            if not self._security.jwt_secret:
                issues.append("JWT secret is required when authentication is enabled")

        return issues


# Create a singleton instance
config_manager = ConfigManager()


# Convenience functions for module-level access
def get_config() -> ConfigManager:
    """Get the singleton ConfigManager instance."""
    return config_manager


def get_settings() -> SettingsConfig:
    """Get settings configuration."""
    return config_manager.get_settings()


def get_security() -> SecurityConfig:
    """Get security configuration."""
    return config_manager.get_security()


def get_details() -> DetailsConfig:
    """Get application details configuration."""
    return config_manager.get_details()


def reload_config() -> None:
    """Reload all configurations from files."""
    config_manager.reload()
