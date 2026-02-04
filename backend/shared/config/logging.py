"""
Centralized structured logging for the backend.
Uses Python's standard logging with JSON formatting for production.

FIX-03: Integrated Correlation ID support for distributed tracing.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from shared.config.settings import settings


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    Outputs logs in a format easily parseable by log aggregation tools.
    
    FIX-03: Includes request_id (correlation ID) in output.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # FIX-03: Add correlation ID if present
        request_id = getattr(record, 'request_id', None)
        if request_id and request_id != '-':
            log_data["request_id"] = request_id

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
    
    FIX-03: Includes correlation ID in output.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%H:%M:%S")

        # FIX-03: Include correlation ID if present
        request_id = getattr(record, 'request_id', None)
        if request_id and request_id != '-':
            request_id_str = f"{self.DIM}[{request_id[:8]}]{self.RESET} "
        else:
            request_id_str = ""

        # Base message
        message = f"{color}[{timestamp}] {record.levelname:8}{self.RESET} {request_id_str}{record.name}: {record.getMessage()}"

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
    
    FIX-03: Integrates CorrelationIdFilter for distributed tracing.
    """
    # Import here to avoid circular imports
    from shared.infrastructure.correlation import CorrelationIdFilter
    
    # Determine log level from settings
    log_level = logging.DEBUG if settings.debug else logging.INFO

    # Create handler with correlation filter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.addFilter(CorrelationIdFilter())  # FIX-03: Add correlation filter

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
    
    logging.getLogger("shared.infrastructure.correlation").info(
        "Correlation ID logging integrated (FIX-03)"
    )


def get_logger(name: str) -> StructuredLogger:
    """
    Get a logger instance with the given name.

    Usage:
        from shared.logging import get_logger
        logger = get_logger(__name__)

        # SHARED-HIGH-02 FIX: Use mask_email() for PII protection
        logger.info("User logged in", user_id=123, email=mask_email("user@example.com"))
        logger.error("Failed to process payment", check_id=456, exc_info=True)
    """
    return logging.getLogger(name)  # type: ignore


def mask_email(email: str | None) -> str:
    """
    SHARED-HIGH-02 FIX: Mask email address for logging to protect PII.

    Converts "user@example.com" to "us***@example.com"
    Only shows first 2 characters of local part and full domain for debugging.

    Args:
        email: The email address to mask.

    Returns:
        Masked email string safe for logging.
    """
    if not email:
        return "<no-email>"

    try:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = local[0] + "***"
        else:
            masked_local = local[:2] + "***"
        return f"{masked_local}@{domain}"
    except ValueError:
        # Not a valid email format
        return "***@invalid"


def mask_jti(jti: str | None) -> str:
    """
    SHARED-MED-02 FIX: Mask JWT ID (jti) for logging.

    Shows only first 8 characters for correlation while protecting full token ID.
    Example: "abc12345-6789-..." → "abc12345..."

    Args:
        jti: The JWT ID to mask.

    Returns:
        Masked JTI string safe for logging.
    """
    if not jti:
        return "<no-jti>"

    if len(jti) <= 8:
        return jti
    return f"{jti[:8]}..."


def mask_user_id(user_id: int | str | None) -> str:
    """
    SHARED-MED-02 FIX: Mask user ID for logging in sensitive contexts.

    For general logging, user IDs can be shown. Use this function when
    logging in security-sensitive contexts where correlation attacks are possible.

    Args:
        user_id: The user ID to mask.

    Returns:
        Masked user ID string safe for logging.
    """
    if user_id is None:
        return "<no-user>"

    # Convert to string and show first 2 digits + ***
    user_str = str(user_id)
    if len(user_str) <= 2:
        return user_str[0] + "***"
    return f"{user_str[:2]}***"


# Pre-configured loggers for common modules
rest_api_logger = get_logger("rest_api")
ws_gateway_logger = get_logger("ws_gateway")
billing_logger = get_logger("rest_api.billing")
kitchen_logger = get_logger("rest_api.kitchen")
diner_logger = get_logger("rest_api.diner")
auth_logger = get_logger("rest_api.auth")
waiter_logger = get_logger("rest_api.waiter")

# SEC-LOW-03 FIX: Dedicated security audit logger
security_audit_logger = get_logger("security.audit")


# =============================================================================
# SEC-LOW-03 FIX: Security Audit Logging Functions
# =============================================================================


def audit_ws_connection(
    event_type: str,
    endpoint: str,
    user_id: int | str | None = None,
    session_id: int | None = None,
    origin: str | None = None,
    reason: str | None = None,
    **extra: Any,
) -> None:
    """
    SEC-LOW-03 FIX: Log WebSocket connection security events.

    Creates structured audit trail for connection lifecycle and security events.

    Args:
        event_type: Type of event (CONNECT, DISCONNECT, AUTH_FAILED, RATE_LIMITED, etc.)
        endpoint: WebSocket endpoint (/ws/waiter, /ws/kitchen, etc.)
        user_id: User ID (for authenticated connections)
        session_id: Session ID (for diner connections)
        origin: Origin header value
        reason: Reason for event (especially for failures)
        **extra: Additional context data
    """
    security_audit_logger.info(
        f"WS_AUDIT: {event_type}",
        event_type=event_type,
        endpoint=endpoint,
        user_id=user_id,
        session_id=session_id,
        origin=origin,
        reason=reason,
        **extra,
    )


def audit_auth_event(
    event_type: str,
    user_id: int | str | None = None,
    email: str | None = None,
    success: bool = True,
    reason: str | None = None,
    ip_address: str | None = None,
    **extra: Any,
) -> None:
    """
    SEC-LOW-03 FIX: Log authentication security events.

    Creates audit trail for login attempts, token operations, etc.

    Args:
        event_type: Type of event (LOGIN, LOGOUT, TOKEN_REFRESH, TOKEN_REVOKED, etc.)
        user_id: User ID (if known)
        email: Email address (masked automatically)
        success: Whether the operation succeeded
        reason: Reason for failure (if applicable)
        ip_address: Client IP address
        **extra: Additional context data
    """
    log_level = logging.INFO if success else logging.WARNING

    security_audit_logger._log_with_data(
        log_level,
        f"AUTH_AUDIT: {event_type}",
        args=(),
        event_type=event_type,
        user_id=user_id,
        email=mask_email(email) if email else None,
        success=success,
        reason=reason,
        ip_address=ip_address,
        **extra,
    )


def audit_rate_limit_event(
    context: str,
    identifier: int | str,
    limit: int,
    window: int,
    ip_address: str | None = None,
    **extra: Any,
) -> None:
    """
    SEC-LOW-03 FIX: Log rate limiting events.

    Args:
        context: Context (waiter, kitchen, diner, login)
        identifier: User ID, session ID, or email being rate limited
        limit: Rate limit that was exceeded
        window: Time window in seconds
        ip_address: Client IP address
        **extra: Additional context data
    """
    security_audit_logger.warning(
        f"RATE_LIMIT_AUDIT: {context}",
        context=context,
        identifier=identifier,
        limit=limit,
        window=window,
        ip_address=ip_address,
        **extra,
    )


def audit_token_event(
    event_type: str,
    user_id: int | str | None = None,
    jti_hash: str | None = None,
    token_type: str | None = None,
    **extra: Any,
) -> None:
    """
    SEC-LOW-03 FIX: Log token lifecycle events.

    Args:
        event_type: Type of event (BLACKLISTED, REVOKED, REVALIDATION_FAILED, etc.)
        user_id: User ID associated with token
        jti_hash: Hashed JTI for correlation (not raw JTI)
        token_type: Token type (access, refresh, table)
        **extra: Additional context data
    """
    security_audit_logger.info(
        f"TOKEN_AUDIT: {event_type}",
        event_type=event_type,
        user_id=user_id,
        jti_hash=jti_hash,
        token_type=token_type,
        **extra,
    )
