#!/usr/bin/env python3
"""
Logging Configuration Module for Filefy Application.

This module provides centralized logging configuration that integrates
with the application's configuration system.

Features:
- Configurable log levels
- File and console handlers
- Rotating file handler support
- JSON log format option

Usage:
    from scripts.logger import setup_logging, get_logger

    # Setup logging (usually called once at startup)
    setup_logging()

    # Get a logger for a specific module
    logger = get_logger(__name__)
    logger.info("Application started")
"""

import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Add parent directory to path for imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to log output for console handlers.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: Optional[str] = None, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with optional colors."""
        formatted = super().format(record)

        if self.use_colors and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            formatted = f"{color}{formatted}{self.RESET}"

        return formatted


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs log records as JSON objects.
    Useful for log aggregation systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        import json

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_entry.update(record.extra)

        return json.dumps(log_entry)


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    use_colors: bool = True,
    use_json: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (relative to base directory)
        log_format: Log format string
        use_colors: Enable colored console output
        use_json: Use JSON format for file logs
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup files to keep
    """
    # Try to get settings from config
    try:
        from filefy.config import get_settings
        settings = get_settings()
        level = level or settings.log_level
        log_file = log_file or settings.log_path
        log_format = log_format or settings.log_format
    except ImportError:
        level = level or "INFO"
        log_file = log_file or "logs/app.log"
        log_format = log_format or "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    if use_colors:
        console_formatter = ColoredFormatter(log_format, use_colors=True)
    else:
        console_formatter = logging.Formatter(log_format)

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Create file handler
    if log_file:
        log_path = BASE_DIR / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        if use_json:
            file_formatter = JSONFormatter()
        else:
            file_formatter = logging.Formatter(log_format)

        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Log startup message
    root_logger.info(f"Logging initialized (level={level})")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that adds context information to log messages.
    """

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add extra context to log message."""
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def create_request_logger(request_id: str) -> LoggerAdapter:
    """
    Create a logger adapter with request context.

    Args:
        request_id: Unique request identifier

    Returns:
        Logger adapter with request context
    """
    logger = get_logger("filefy.request")
    return LoggerAdapter(logger, {"request_id": request_id})


# Configure logging when module is imported
def _init_logging() -> None:
    """Initialize logging if not already configured."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        setup_logging()


# Auto-initialize on import
_init_logging()



