"""
Centralized structured logging for the backend.
Uses Python's standard logging with JSON formatting for production.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from shared.settings import settings


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    Outputs logs in a format easily parseable by log aggregation tools.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra_data") and record.extra_data:
            log_data["data"] = record.extra_data

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add source location in debug mode
        if settings.debug:
            log_data["source"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log_data, default=str)


class DevelopmentFormatter(logging.Formatter):
    """
    Human-readable formatter for development.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Base message
        message = f"{color}[{timestamp}] {record.levelname:8}{self.RESET} {record.name}: {record.getMessage()}"

        # Add extra data if present
        if hasattr(record, "extra_data") and record.extra_data:
            data_str = " | ".join(f"{k}={v}" for k, v in record.extra_data.items())
            message += f" ({data_str})"

        # Add exception info if present
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"

        return message


class StructuredLogger(logging.Logger):
    """
    Custom logger that supports structured data.
    """

    def _log_with_data(
        self,
        level: int,
        msg: str,
        args: tuple,
        exc_info: Any = None,
        extra: dict | None = None,
        **kwargs: Any,
    ) -> None:
        """Log with optional structured data."""
        if extra is None:
            extra = {}
        extra["extra_data"] = kwargs if kwargs else None
        super()._log(level, msg, args, exc_info=exc_info, extra=extra)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log_with_data(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log_with_data(logging.INFO, msg, args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log_with_data(logging.WARNING, msg, args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        exc_info = kwargs.pop("exc_info", None)
        self._log_with_data(logging.ERROR, msg, args, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        exc_info = kwargs.pop("exc_info", None)
        self._log_with_data(logging.CRITICAL, msg, args, exc_info=exc_info, **kwargs)


# Set custom logger class
logging.setLoggerClass(StructuredLogger)


def setup_logging() -> None:
    """
    Configure logging for the application.
    Call this once at application startup.
    """
    # Determine log level from settings
    log_level = logging.DEBUG if settings.debug else logging.INFO

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Use appropriate formatter based on environment
    if settings.environment == "production":
        formatter = StructuredFormatter()
    else:
        formatter = DevelopmentFormatter()

    handler.setFormatter(formatter)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """
    Get a logger instance with the given name.

    Usage:
        from shared.logging import get_logger
        logger = get_logger(__name__)

        logger.info("User logged in", user_id=123, email="user@example.com")
        logger.error("Failed to process payment", check_id=456, exc_info=True)
    """
    return logging.getLogger(name)  # type: ignore


# Pre-configured loggers for common modules
rest_api_logger = get_logger("rest_api")
ws_gateway_logger = get_logger("ws_gateway")
billing_logger = get_logger("rest_api.billing")
kitchen_logger = get_logger("rest_api.kitchen")
diner_logger = get_logger("rest_api.diner")
auth_logger = get_logger("rest_api.auth")
waiter_logger = get_logger("rest_api.waiter")
