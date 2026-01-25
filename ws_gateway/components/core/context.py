"""
WebSocket Context for audit logging.

Encapsulates connection metadata for consistent audit logging.
Eliminates data clumps in audit_ws_connection calls.

ARCH-SMELL-09 FIX: Replaced repeated audit parameters with context object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket


# MED-WS-16 FIX: Pattern to remove control characters from log data
# MED-02 FIX: Extended to include Unicode direction overrides and more control chars
_CONTROL_CHAR_PATTERN = re.compile(
    r'[\x00-\x1f\x7f-\x9f'  # ASCII control characters
    r'\u200b-\u200f'  # Zero-width and direction marks
    r'\u202a-\u202e'  # Bidirectional text formatting (RTL override, etc.)
    r'\u2066-\u2069'  # Isolate formatting characters
    r'\ufeff]'  # BOM / Zero-width no-break space
)


def sanitize_log_data(data: str, max_length: int = 100) -> str:
    """
    Sanitize user-provided data before logging.

    MED-02 FIX: Enhanced to handle:
    - Control characters (ASCII and Unicode)
    - JSON-dangerous characters (quotes, backslashes)
    - Unicode direction override characters (RTL attacks)

    MED-AUD-03 FIX: Truncate BEFORE escaping to ensure consistent output length.
    Previously, escaping could expand the string, causing inconsistent truncation.

    Args:
        data: Raw user data.
        max_length: Maximum length to include in logs.

    Returns:
        Sanitized, truncated string safe for structured logging.
    """
    # MED-AUD-03 FIX: Truncate FIRST to ensure consistent length
    # This prevents escape sequences from being cut in half
    truncated = data[:max_length] if len(data) > max_length else data
    was_truncated = len(data) > max_length

    # Remove control characters and direction overrides
    sanitized = _CONTROL_CHAR_PATTERN.sub('', truncated)

    # MED-02 FIX: Escape JSON-dangerous characters
    # Replace backslashes first to avoid double-escaping
    sanitized = sanitized.replace('\\', '\\\\')
    sanitized = sanitized.replace('"', '\\"')
    sanitized = sanitized.replace('\n', '\\n')
    sanitized = sanitized.replace('\r', '\\r')
    sanitized = sanitized.replace('\t', '\\t')

    # Add truncation indicator if needed
    if was_truncated:
        return sanitized + "..."
    return sanitized


@dataclass
class WebSocketContext:
    """
    Context object for WebSocket connection metadata.

    Encapsulates all metadata needed for audit logging, reducing
    the number of parameters passed to logging functions.

    Usage:
        ctx = WebSocketContext.from_jwt_claims(websocket, claims, "/ws/waiter")
        ctx.audit("CONNECT")
        # ... later
        ctx.audit("DISCONNECT", reason="client_disconnect")
    """

    # Connection metadata
    endpoint: str
    origin: str | None = None

    # User authentication (JWT)
    user_id: int | None = None
    tenant_id: int | None = None
    roles: list[str] = field(default_factory=list)
    branch_ids: list[int] = field(default_factory=list)
    sector_ids: list[int] = field(default_factory=list)

    # Diner authentication (table token)
    session_id: int | None = None
    table_id: int | None = None
    branch_id: int | None = None

    # Connection state
    is_admin: bool = False

    @classmethod
    def from_websocket(cls, websocket: "WebSocket", endpoint: str) -> "WebSocketContext":
        """
        Create context from a WebSocket connection.

        Only extracts basic connection info (origin).
        Call update_from_jwt_claims() or update_from_table_token() to add auth info.

        Args:
            websocket: The WebSocket connection.
            endpoint: The endpoint path (e.g., "/ws/waiter").

        Returns:
            WebSocketContext with basic connection info.
        """
        return cls(
            endpoint=endpoint,
            origin=websocket.headers.get("origin"),
        )

    @classmethod
    def from_jwt_claims(
        cls,
        websocket: "WebSocket",
        claims: dict[str, Any],
        endpoint: str,
        sector_ids: list[int] | None = None,
        is_admin: bool = False,
    ) -> "WebSocketContext":
        """
        Create context from JWT claims.

        Args:
            websocket: The WebSocket connection.
            claims: JWT claims dict.
            endpoint: The endpoint path.
            sector_ids: Optional sector IDs for waiters.
            is_admin: Whether this is an admin connection.

        Returns:
            WebSocketContext populated from JWT claims.
        """
        return cls(
            endpoint=endpoint,
            origin=websocket.headers.get("origin"),
            user_id=int(claims.get("sub", 0)),
            tenant_id=int(claims.get("tenant_id", 0)),
            roles=list(claims.get("roles", [])),
            branch_ids=list(claims.get("branch_ids", [])),
            sector_ids=sector_ids or [],
            is_admin=is_admin,
        )

    @classmethod
    def from_table_token(
        cls,
        websocket: "WebSocket",
        token_data: dict[str, Any],
        endpoint: str,
    ) -> "WebSocketContext":
        """
        Create context from table token data.

        Args:
            websocket: The WebSocket connection.
            token_data: Table token data dict.
            endpoint: The endpoint path.

        Returns:
            WebSocketContext populated from table token.
        """
        return cls(
            endpoint=endpoint,
            origin=websocket.headers.get("origin"),
            session_id=token_data.get("session_id"),
            table_id=token_data.get("table_id"),
            branch_id=token_data.get("branch_id"),
        )

    def to_audit_dict(self, event_type: str, **extra: Any) -> dict[str, Any]:
        """
        Convert to dictionary for audit logging.

        Only includes non-None fields to reduce log noise.

        Args:
            event_type: The audit event type (e.g., "CONNECT", "DISCONNECT").
            **extra: Additional fields to include (e.g., reason="timeout").

        Returns:
            Dictionary suitable for structured logging.
        """
        result: dict[str, Any] = {
            "event_type": event_type,
            "endpoint": self.endpoint,
        }

        # Add optional fields only if they have values
        if self.origin:
            result["origin"] = self.origin
        if self.user_id:
            result["user_id"] = self.user_id
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.roles:
            result["roles"] = self.roles
        if self.branch_ids:
            result["branches"] = self.branch_ids
        if self.sector_ids:
            result["sectors"] = self.sector_ids
        if self.session_id:
            result["session_id"] = self.session_id
        if self.table_id:
            result["table_id"] = self.table_id
        if self.branch_id:
            result["branch_id"] = self.branch_id
        if self.is_admin:
            result["is_admin"] = True

        # Add extra fields
        result.update(extra)

        return result

    def audit(
        self,
        event_type: str,
        logger_func: Any = None,
        **extra: Any,
    ) -> None:
        """
        Log an audit event.

        Uses structured logging with all context fields.

        Args:
            event_type: The audit event type.
            logger_func: Optional custom logger function (default: shared.logging.audit_ws_connection).
            **extra: Additional fields to log.
        """
        if logger_func is None:
            from shared.config.logging import audit_ws_connection
            logger_func = audit_ws_connection

        audit_dict = self.to_audit_dict(event_type, **extra)
        logger_func(**audit_dict)

    @property
    def identifier(self) -> str:
        """
        Get a human-readable identifier for this connection.

        Returns user_id for authenticated users, session_id for diners.
        """
        if self.user_id:
            return f"user:{self.user_id}"
        if self.session_id:
            return f"session:{self.session_id}"
        return "anonymous"

    @property
    def pseudo_user_id(self) -> int:
        """
        Get pseudo user ID for connection manager.

        Diners use negative session_id to avoid collision with user IDs.
        LOW-WS-02 FIX: Documented the pseudo user ID pattern.
        """
        if self.user_id:
            return self.user_id
        if self.session_id:
            return -self.session_id
        return 0
