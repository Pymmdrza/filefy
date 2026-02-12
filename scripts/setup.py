#!/usr/bin/env python3
"""
Application Setup and Initialization Script for Filefy.

This script performs initial setup tasks:
- Creates required directories (logs, uploads)
- Validates configuration files
- Checks system requirements
- Sets up logging

Usage:
    python -m scripts.setup
    python scripts/setup.py
"""

import os
import sys
import platform
import logging
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import config_manager, get_settings


class SetupManager:
    """
    Handles application setup and initialization.
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize the SetupManager.

        Args:
            base_path: Base path for the application
        """
        self.base_path = base_path or BASE_DIR
        self.os_type = platform.system().lower()
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.success: List[str] = []

    def run(self) -> bool:
        """
        Run all setup tasks.

        Returns:
            True if setup was successful, False if there were errors
        """
        print("=" * 60)
        print("Filefy Application Setup")
        print("=" * 60)
        print()

        # Run setup tasks
        self._check_python_version()
        self._create_directories()
        self._validate_configs()
        self._setup_logging()
        self._check_dependencies()

        # Print summary
        self._print_summary()

        return len(self.errors) == 0

    def _check_python_version(self) -> None:
        """Check if Python version meets requirements."""
        print("Checking Python version...")

        version = sys.version_info
        required_version = (3, 8)

        if version >= required_version:
            self.success.append(
                f"Python version {version.major}.{version.minor}.{version.micro} - OK"
            )
        else:
            self.errors.append(
                f"Python {required_version[0]}.{required_version[1]}+ required, "
                f"but {version.major}.{version.minor} found"
            )

    def _create_directories(self) -> None:
        """Create required application directories."""
        print("Creating required directories...")

        directories = [
            self.base_path / "logs",
            self.base_path / "uploads",
        ]

        for dir_path in directories:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                if os.access(dir_path, os.W_OK):
                    self.success.append(f"Directory created: {dir_path}")
                else:
                    self.warnings.append(f"Directory not writable: {dir_path}")
            except PermissionError as e:
                self.errors.append(f"Cannot create directory {dir_path}: {e}")
            except OSError as e:
                self.errors.append(f"Error creating {dir_path}: {e}")

    def _validate_configs(self) -> None:
        """Validate configuration files."""
        print("Validating configuration files...")

        config_files = [
            "config.json",
            "settings.json",
            "security.json",
            "details.json",
            "build.json",
        ]

        config_dir = self.base_path / "config"

        for filename in config_files:
            filepath = config_dir / filename
            if not filepath.exists():
                self.warnings.append(f"Config file missing: {filename}")
            elif not os.access(filepath, os.R_OK):
                self.errors.append(f"Config file not readable: {filename}")
            else:
                self.success.append(f"Config file OK: {filename}")

        # Validate config manager
        issues = config_manager.validate()
        for issue in issues:
            self.warnings.append(f"Config validation: {issue}")

    def _setup_logging(self) -> None:
        """Setup application logging."""
        print("Setting up logging...")

        settings = get_settings()
        log_path = self.base_path / settings.log_path

        try:
            log_dir = log_path.parent
            log_dir.mkdir(parents=True, exist_ok=True)

            # Create log file if it doesn't exist
            if not log_path.exists():
                log_path.touch()

            # Configure logging
            logging.basicConfig(
                level=getattr(logging, settings.log_level.upper(), logging.INFO),
                format=settings.log_format,
                handlers=[
                    logging.FileHandler(log_path),
                    logging.StreamHandler(),
                ],
            )

            self.success.append(f"Logging configured: {log_path}")
        except Exception as e:
            self.warnings.append(f"Could not setup logging: {e}")

    def _check_dependencies(self) -> None:
        """Check if required dependencies are installed."""
        print("Checking dependencies...")

        required_packages = [
            ("flask", "Flask"),
            ("requests", "Requests"),
            ("werkzeug", "Werkzeug"),
        ]

        for package, display_name in required_packages:
            try:
                __import__(package)
                self.success.append(f"Dependency OK: {display_name}")
            except ImportError:
                self.errors.append(f"Missing dependency: {display_name}")

    def _print_summary(self) -> None:
        """Print setup summary."""
        print()
        print("=" * 60)
        print("Setup Summary")
        print("=" * 60)
        print()

        if self.success:
            print("✓ Success:")
            for item in self.success:
                print(f"  - {item}")
            print()

        if self.warnings:
            print("⚠ Warnings:")
            for item in self.warnings:
                print(f"  - {item}")
            print()

        if self.errors:
            print("✗ Errors:")
            for item in self.errors:
                print(f"  - {item}")
            print()

        print("=" * 60)
        if self.errors:
            print("Setup completed with errors. Please fix the issues above.")
        elif self.warnings:
            print("Setup completed with warnings. Application may have issues.")
        else:
            print("Setup completed successfully!")
        print("=" * 60)


def create_default_configs() -> None:
    """Create default configuration files if they don't exist."""
    config_dir = BASE_DIR / "config"

    default_configs = {
        "config.json": {
            "configFiles": {
                "settings": "settings.json",
                "security": "security.json",
                "details": "details.json",
                "build": "build.json",
            },
            "environment": "development",
        },
        "settings.json": {
            "settings": {
                "network": {"host": "0.0.0.0", "port": 5000},
                "fileManager": {
                    "rootDirectory": "~",
                    "maxUploadSize": 10737418240,
                    "allowedExtensions": ["*"],
                },
                "logging": {
                    "level": "INFO",
                    "path": "logs/app.log",
                    "format": "%(asctime)s [%(levelname)s] : %(message)s",
                },
                "permissions": {"read": True, "write": True, "delete": False},
            }
        },
        "security.json": {
            "security": {
                "enableAuthentication": False,
                "jwt": {"secret": "", "expiresIn": "1h"},
                "bcrypt": {"saltRounds": 10},
                "cors": {
                    "origin": "*",
                    "methods": ["GET", "POST", "PUT", "DELETE"],
                    "preflightContinue": False,
                    "optionsSuccessStatus": 204,
                },
                "rateLimit": {"windowMs": 900000, "max": 100},
                "administrator": {"username": "admin", "password": ""},
            }
        },
        "details.json": {
            "appName": "Filefy",
            "version": "1.0.0",
            "programmer": "Mmdrza",
            "email": "pymmdrza@gmail.com",
            "license": "MIT",
            "description": "A professional web-based file manager with dark theme UI",
            "repository": "https://github.com/Pymmdrza/filefy",
        },
        "build.json": {
            "setup": {"path": "setup.py"},
            "requirements": {"path": "requirements.txt"},
            "project": {"path": "pyproject.toml"},
            "readme": {"path": "README.md"},
            "license": {"path": "LICENSE"},
        },
    }

    import json

    for filename, content in default_configs.items():
        filepath = config_dir / filename
        if not filepath.exists():
            print(f"Creating default config: {filename}")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)


def main():
    """Main entry point for setup script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Filefy Application Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--create-configs",
        action="store_true",
        help="Create default configuration files if missing",
    )

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check setup status without making changes",
    )

    args = parser.parse_args()

    if args.create_configs:
        create_default_configs()

    manager = SetupManager()
    success = manager.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()


