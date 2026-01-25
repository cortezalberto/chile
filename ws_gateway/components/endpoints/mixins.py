"""
WebSocket Endpoint Mixins.

ARCH-AUDIT-04: Extracted from ws_endpoint_base.py to follow SRP.
Each mixin handles a single concern for WebSocket endpoints.

Mixins:
    MessageValidationMixin: Message size and rate limit checks
    OriginValidationMixin: WebSocket origin header validation
    JWTRevalidationMixin: Periodic JWT token revalidation

Usage:
    class MyEndpoint(MessageValidationMixin, OriginValidationMixin, WebSocketEndpointBase):
        ...
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol

from fastapi import HTTPException, WebSocket

from ws_gateway.components.core.constants import WSCloseCode

if TYPE_CHECKING:
    from ws_gateway.connection_manager import ConnectionManager
    from ws_gateway.components.core.context import WebSocketContext

logger = logging.getLogger(__name__)


# =============================================================================
# Protocols for mixin dependencies
# =============================================================================


class HasWebSocket(Protocol):
    """Protocol for classes with websocket attribute."""

    websocket: WebSocket
    endpoint_name: str
    context: "WebSocketContext | None"


class HasManager(Protocol):
    """Protocol for classes with manager attribute."""

    manager: "ConnectionManager"


class HasToken(Protocol):
    """Protocol for classes with JWT token."""

    token: str
    jwt_revalidation_interval: float
    _last_jwt_revalidation: float


# =============================================================================
# MessageValidationMixin
# =============================================================================


class MessageValidationMixin:
    """
    Mixin for message validation (size and rate limiting).

    ARCH-AUDIT-04: Extracted from WebSocketEndpointBase.

    Requires:
        - self.websocket: WebSocket
        - self.manager: ConnectionManager
        - self.endpoint_name: str
        - self.context: WebSocketContext | None

    Usage:
        class MyEndpoint(MessageValidationMixin, WebSocketEndpointBase):
            pass
    """

    async def validate_message_size(self: HasWebSocket, data: str) -> bool:
        """
        Validate message size against configured limit.

        Args:
            data: Message data to validate.

        Returns:
            True if valid, False if too large (connection closed).
        """
        from shared.config.settings import settings

        max_size = getattr(settings, "ws_max_message_size", 64 * 1024)

        if len(data) > max_size:
            logger.warning(
                "Message size exceeded limit",
                endpoint=self.endpoint_name,
                identifier=self.context.identifier if self.context else "unknown",
                size=len(data),
                max_size=max_size,
            )
            await self.websocket.close(
                code=WSCloseCode.MESSAGE_TOO_BIG,
                reason="Message too large",
            )
            return False
        return True

    async def check_rate_limit(self: "HasWebSocket & HasManager") -> bool:
        """
        Check rate limit for this connection.

        Returns:
            True if allowed, False if rate limited (connection closed).
        """
        if not await self.manager.check_rate_limit(self.websocket):
            logger.warning(
                "Rate limit exceeded",
                endpoint=self.endpoint_name,
                identifier=self.context.identifier if self.context else "unknown",
            )
            self.manager.record_rate_limit_rejection()
            await self.websocket.close(
                code=WSCloseCode.RATE_LIMITED,
                reason="Rate limit exceeded",
            )
            return False
        return True


# =============================================================================
# OriginValidationMixin
# =============================================================================


class OriginValidationMixin:
    """
    Mixin for WebSocket origin header validation.

    ARCH-AUDIT-04: Extracted from JWTWebSocketEndpoint.

    Requires:
        - self.websocket: WebSocket

    Usage:
        class MyEndpoint(OriginValidationMixin, WebSocketEndpointBase):
            def validate_auth(self):
                if not self.validate_origin():
                    return None
                ...
    """

    def validate_origin(self: HasWebSocket) -> bool:
        """
        Validate WebSocket origin header against allowed origins.

        Uses shared validation function to eliminate duplication.

        Returns:
            True if origin is allowed, False otherwise.
        """
        from shared.config.settings import settings
        from ws_gateway.components.core.constants import validate_websocket_origin

        origin = self.websocket.headers.get("origin")
        return validate_websocket_origin(origin, settings)

    def get_origin(self: HasWebSocket) -> str | None:
        """Get origin header from websocket."""
        return self.websocket.headers.get("origin")


# =============================================================================
# JWTRevalidationMixin
# =============================================================================


class JWTRevalidationMixin:
    """
    Mixin for periodic JWT token revalidation.

    ARCH-AUDIT-04: Extracted from JWTWebSocketEndpoint.

    Detects revoked/expired tokens during long-lived WebSocket connections.

    Requires:
        - self.token: str
        - self.jwt_revalidation_interval: float
        - self._last_jwt_revalidation: float

    Usage:
        class MyEndpoint(JWTRevalidationMixin, WebSocketEndpointBase):
            async def _pre_message_hook(self):
                return await self.revalidate_jwt_if_needed()
    """

    async def revalidate_jwt_if_needed(self: HasToken) -> bool:
        """
        Revalidate JWT if revalidation interval has passed.

        Returns:
            True if token is still valid, False if expired/revoked.
        """
        now = time.time()
        if now - self._last_jwt_revalidation < self.jwt_revalidation_interval:
            return True

        return await self._do_jwt_revalidation()

    async def _do_jwt_revalidation(self: HasToken) -> bool:
        """
        Perform actual JWT revalidation.

        Returns:
            True if valid, False if invalid.
        """
        from shared.security.auth import verify_jwt

        try:
            claims = verify_jwt(self.token)
            if claims.get("type") == "refresh":
                logger.warning("Refresh token detected during revalidation")
                return False
            self._last_jwt_revalidation = time.time()
            return True
        except HTTPException as e:
            logger.debug("JWT revalidation failed", error=str(e.detail))
            return False

    def reset_jwt_revalidation_timer(self: HasToken) -> None:
        """Reset the revalidation timer (e.g., after fresh token verification)."""
        self._last_jwt_revalidation = time.time()


# =============================================================================
# HeartbeatMixin
# =============================================================================


class HeartbeatMixin:
    """
    Mixin for heartbeat handling.

    ARCH-AUDIT-04: Provides heartbeat recording functionality.

    Requires:
        - self.websocket: WebSocket
        - self.manager: ConnectionManager

    Usage:
        class MyEndpoint(HeartbeatMixin, WebSocketEndpointBase):
            async def _message_loop(self):
                ...
                await self.record_heartbeat()
    """

    async def record_heartbeat(self: "HasWebSocket & HasManager") -> None:
        """Record heartbeat for this connection."""
        await self.manager.record_heartbeat(self.websocket)


# =============================================================================
# ConnectionLifecycleMixin
# =============================================================================


class ConnectionLifecycleMixin:
    """
    Mixin for connection lifecycle logging.

    ARCH-AUDIT-04: Provides standardized lifecycle event logging.

    Requires:
        - self.endpoint_name: str
        - self.context: WebSocketContext | None

    Usage:
        class MyEndpoint(ConnectionLifecycleMixin, WebSocketEndpointBase):
            async def run(self):
                ...
                self.log_connect()
    """

    def log_connect(self: HasWebSocket) -> None:
        """Log connection event."""
        endpoint_type = self.endpoint_name.split("/")[-1].title()
        logger.info(
            f"{endpoint_type} connected",
            **self.context.to_audit_dict("CONNECT") if self.context else {},
        )
        if self.context:
            self.context.audit("CONNECT")

    def log_disconnect(self: HasWebSocket, reason: str = "client_disconnect") -> None:
        """Log disconnection event."""
        endpoint_type = self.endpoint_name.split("/")[-1].title()
        logger.info(
            f"{endpoint_type} disconnected",
            **(
                self.context.to_audit_dict("DISCONNECT", reason=reason)
                if self.context
                else {}
            ),
        )
        if self.context:
            self.context.audit("DISCONNECT", reason=reason)

    def log_connect_rejected(self: HasWebSocket, reason: str) -> None:
        """Log connection rejection event."""
        logger.warning(
            "Connection rejected",
            endpoint=self.endpoint_name,
            identifier=self.context.identifier if self.context else "unknown",
            reason=reason,
        )
        if self.context:
            self.context.audit("CONNECT_REJECTED", reason=reason)


# =============================================================================
# Exports
# =============================================================================


__all__ = [
    "MessageValidationMixin",
    "OriginValidationMixin",
    "JWTRevalidationMixin",
    "HeartbeatMixin",
    "ConnectionLifecycleMixin",
    # Protocols
    "HasWebSocket",
    "HasManager",
    "HasToken",
]
