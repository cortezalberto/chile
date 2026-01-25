"""
WebSocket Endpoint Base Class.

Provides common functionality for all WebSocket endpoints,
eliminating code duplication across waiter, kitchen, admin, and diner endpoints.

ARCH-AP-08 FIX: Eliminated copy-paste programming in endpoints.
ARCH-AUDIT-04 FIX: Refactored to use mixins for SRP compliance.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from ws_gateway.components.core.constants import WSCloseCode, WSConstants
from ws_gateway.components.connection.heartbeat import handle_heartbeat
from ws_gateway.components.core.context import WebSocketContext, sanitize_log_data
from ws_gateway.components.endpoints.mixins import (
    MessageValidationMixin,
    OriginValidationMixin,
    JWTRevalidationMixin,
    HeartbeatMixin,
    ConnectionLifecycleMixin,
)

if TYPE_CHECKING:
    from ws_gateway.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class WebSocketEndpointBase(
    MessageValidationMixin,
    HeartbeatMixin,
    ConnectionLifecycleMixin,
    ABC,
):
    """
    Base class for WebSocket endpoints.

    ARCH-AUDIT-04 FIX: Now uses mixins for SRP compliance:
    - MessageValidationMixin: Message size and rate limit checks
    - HeartbeatMixin: Heartbeat recording
    - ConnectionLifecycleMixin: Lifecycle logging

    Encapsulates common patterns:
    - Connection lifecycle (accept, message loop, disconnect)
    - Rate limiting and message size validation
    - Heartbeat handling
    - Audit logging

    Subclasses implement:
    - validate_auth(): Validate authentication (JWT or table token)
    - get_context(): Create WebSocketContext from auth
    - register_connection(): Register with ConnectionManager
    - handle_message(): Process non-heartbeat messages

    Usage:
        class WaiterEndpoint(WebSocketEndpointBase):
            async def validate_auth(self):
                return verify_jwt(self.token)
            # ... implement abstract methods

        endpoint = WaiterEndpoint(websocket, manager, token)
        await endpoint.run()
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: "ConnectionManager",
        endpoint_name: str,
        receive_timeout: float = WSConstants.WS_RECEIVE_TIMEOUT,
        jwt_revalidation_interval: float = WSConstants.JWT_REVALIDATION_INTERVAL,
    ):
        """
        Initialize the endpoint handler.

        Args:
            websocket: The WebSocket connection.
            manager: ConnectionManager instance.
            endpoint_name: Name for logging (e.g., "/ws/waiter").
            receive_timeout: Timeout for receiving messages.
            jwt_revalidation_interval: Interval for JWT revalidation.
        """
        self.websocket = websocket
        self.manager = manager
        self.endpoint_name = endpoint_name
        self.receive_timeout = receive_timeout
        self.jwt_revalidation_interval = jwt_revalidation_interval

        self.context: WebSocketContext | None = None
        self._last_jwt_revalidation = time.time()
        self._is_running = False

    @abstractmethod
    async def validate_auth(self) -> dict[str, Any] | None:
        """
        Validate authentication for this connection.

        Returns:
            Auth data (JWT claims or table token data), or None if invalid.
            If invalid, should close the WebSocket and return None.
        """
        pass

    @abstractmethod
    async def create_context(self, auth_data: dict[str, Any]) -> WebSocketContext:
        """
        Create WebSocketContext from authentication data.

        Args:
            auth_data: Result from validate_auth().

        Returns:
            WebSocketContext with connection metadata.
        """
        pass

    @abstractmethod
    async def register_connection(self, context: WebSocketContext) -> None:
        """
        Register the connection with ConnectionManager.

        Args:
            context: WebSocketContext with connection metadata.

        Raises:
            ConnectionError: If registration fails.
        """
        pass

    @abstractmethod
    async def unregister_connection(self, context: WebSocketContext) -> None:
        """
        Unregister the connection on disconnect.

        Args:
            context: WebSocketContext with connection metadata.
        """
        pass

    async def handle_message(self, data: str) -> None:
        """
        Handle a non-heartbeat message.

        Override this to handle custom messages (e.g., refresh_sectors).
        Default implementation logs unknown messages.

        Args:
            data: The message data.
        """
        logger.debug(
            "Unknown message received",
            endpoint=self.endpoint_name,
            identifier=self.context.identifier if self.context else "unknown",
            message=sanitize_log_data(data),
        )

    async def revalidate_jwt(self, token: str) -> bool:
        """
        Revalidate JWT if interval has passed.

        Override this for endpoints that use table tokens instead of JWT.

        Args:
            token: The JWT token to revalidate.

        Returns:
            True if token is still valid, False if expired/revoked.
        """
        return True  # Default: no JWT revalidation

    async def run(self) -> None:
        """
        Main entry point - run the WebSocket endpoint.

        Handles the complete lifecycle:
        1. Validate authentication
        2. Create context
        3. Register connection
        4. Message loop
        5. Unregister on disconnect
        """
        # Step 1: Validate authentication
        auth_data = await self.validate_auth()
        if auth_data is None:
            return  # Auth failed, connection already closed

        # Step 2: Create context
        self.context = await self.create_context(auth_data)

        # Step 3: Register connection
        try:
            await self.register_connection(self.context)
        except ConnectionError as e:
            # ARCH-AUDIT-04 FIX: Use mixin for lifecycle logging
            self.log_connect_rejected(str(e))
            return
        except Exception as e:
            logger.error(
                "Unexpected error during connection",
                endpoint=self.endpoint_name,
                identifier=self.context.identifier,
                error=str(e),
            )
            return

        # ARCH-AUDIT-04 FIX: Use mixin for lifecycle logging
        self.log_connect()

        # Step 4: Message loop
        self._is_running = True
        try:
            await self._message_loop()
        except WebSocketDisconnect:
            # ARCH-AUDIT-04 FIX: Use mixin for lifecycle logging
            self.log_disconnect("client_disconnect")
        finally:
            # Step 5: Unregister
            self._is_running = False
            await self.unregister_connection(self.context)

    async def _pre_message_hook(self) -> bool:
        """
        Hook called before processing each message.

        AP-02 FIX: Override this for pre-message checks (e.g., JWT revalidation).
        Subclasses can add validation logic here instead of duplicating _message_loop.

        Returns:
            True to continue processing, False to close connection.
        """
        return True

    async def _message_loop(self) -> None:
        """
        Main message processing loop.

        AP-02 FIX: Refactored to use _pre_message_hook() for extensibility.
        Subclasses override the hook instead of the entire loop.

        Handles:
        - Receive with timeout
        - Message size validation
        - Rate limiting
        - Heartbeat tracking
        - Pre-message hook (JWT revalidation for JWT endpoints)
        - Heartbeat responses
        - Custom message handling
        """
        while self._is_running:
            # Receive with timeout
            data = await self._receive_with_timeout()
            if data is None:
                logger.info(
                    "Connection timed out (no messages)",
                    endpoint=self.endpoint_name,
                    identifier=self.context.identifier if self.context else "unknown",
                    timeout=self.receive_timeout,
                )
                await self.websocket.close(
                    code=WSCloseCode.NORMAL,
                    reason="Connection timeout",
                )
                break

            # ARCH-AUDIT-04 FIX: Use mixin methods
            # Validate message size
            if not await self.validate_message_size(data):
                break

            # Check rate limit
            if not await self.check_rate_limit():
                break

            # Record heartbeat (via HeartbeatMixin)
            await self.record_heartbeat()

            # AP-02 FIX: Call pre-message hook (JWT revalidation, etc.)
            if not await self._pre_message_hook():
                break

            # Handle heartbeat messages
            if await handle_heartbeat(self.websocket, data):
                continue

            # Handle custom messages
            await self.handle_message(data)

    async def _receive_with_timeout(self) -> str | None:
        """
        Receive message with timeout.

        Returns:
            Message data, or None if timeout.
        """
        try:
            return await asyncio.wait_for(
                self.websocket.receive_text(),
                timeout=self.receive_timeout,
            )
        except asyncio.TimeoutError:
            return None

    # ARCH-AUDIT-04 FIX: _validate_message_size and _check_rate_limit
    # moved to MessageValidationMixin (validate_message_size, check_rate_limit)


class JWTWebSocketEndpoint(
    OriginValidationMixin,
    JWTRevalidationMixin,
    WebSocketEndpointBase,
):
    """
    Base class for JWT-authenticated WebSocket endpoints.

    ARCH-AUDIT-04 FIX: Now uses mixins for SRP compliance:
    - OriginValidationMixin: WebSocket origin validation
    - JWTRevalidationMixin: Periodic JWT token revalidation

    Adds JWT-specific functionality:
    - Token validation with required roles
    - Periodic JWT revalidation

    Subclasses: WaiterEndpoint, KitchenEndpoint, AdminEndpoint
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: "ConnectionManager",
        endpoint_name: str,
        token: str,
        required_roles: list[str],
        **kwargs: Any,
    ):
        """
        Initialize JWT endpoint handler.

        Args:
            websocket: The WebSocket connection.
            manager: ConnectionManager instance.
            endpoint_name: Name for logging.
            token: JWT token from query parameter.
            required_roles: Roles allowed to connect.
            **kwargs: Additional args for base class.
        """
        super().__init__(websocket, manager, endpoint_name, **kwargs)
        self.token = token
        self.required_roles = required_roles
        self._claims: dict[str, Any] | None = None

    async def validate_auth(self) -> dict[str, Any] | None:
        """
        Validate JWT token and roles.

        Returns:
            JWT claims if valid, None if invalid.
        """
        from shared.security.auth import verify_jwt
        from shared.config.logging import audit_ws_connection

        origin = self.websocket.headers.get("origin")

        # ARCH-AUDIT-04 FIX: Use mixin method for origin validation
        if not self.validate_origin():
            logger.warning(
                "WebSocket connection rejected - invalid origin",
                origin=origin,
            )
            audit_ws_connection(
                event_type="AUTH_FAILED",
                endpoint=self.endpoint_name,
                origin=origin,
                reason="invalid_origin",
            )
            await self.websocket.close(
                code=WSCloseCode.FORBIDDEN,
                reason="Origin not allowed",
            )
            return None

        # Verify JWT
        try:
            claims = verify_jwt(self.token)
        except HTTPException as e:
            logger.warning(
                "WebSocket JWT validation failed",
                error=str(e.detail),
                origin=origin,
            )
            audit_ws_connection(
                event_type="AUTH_FAILED",
                endpoint=self.endpoint_name,
                origin=origin,
                reason="jwt_validation_failed",
            )
            await self.websocket.close(
                code=WSCloseCode.AUTH_FAILED,
                reason="Authentication failed",
            )
            return None

        # Reject refresh tokens
        if claims.get("type") == "refresh":
            logger.warning("Refresh token used for WebSocket authentication attempt")
            audit_ws_connection(
                event_type="AUTH_FAILED",
                endpoint=self.endpoint_name,
                user_id=claims.get("sub"),
                origin=origin,
                reason="refresh_token_used",
            )
            await self.websocket.close(
                code=WSCloseCode.AUTH_FAILED,
                reason="Authentication failed",
            )
            return None

        # Verify roles
        roles = claims.get("roles", [])
        if not any(role in roles for role in self.required_roles):
            logger.warning(
                "WebSocket connection rejected - insufficient role",
                user_roles=roles,
                required_roles=self.required_roles,
            )
            audit_ws_connection(
                event_type="AUTH_FAILED",
                endpoint=self.endpoint_name,
                user_id=claims.get("sub"),
                origin=origin,
                reason="insufficient_role",
                user_roles=roles,
                required_roles=self.required_roles,
            )
            await self.websocket.close(
                code=WSCloseCode.FORBIDDEN,
                reason="Access denied",
            )
            return None

        self._claims = claims
        return claims

    # ARCH-AUDIT-04 FIX: _validate_origin moved to OriginValidationMixin (validate_origin)

    # ARCH-AUDIT-04 FIX: revalidate_jwt moved to JWTRevalidationMixin

    async def _pre_message_hook(self) -> bool:
        """
        AP-02 FIX: JWT revalidation via hook instead of duplicating _message_loop.
        ARCH-AUDIT-04 FIX: Now uses JWTRevalidationMixin method.

        Performs periodic JWT revalidation to detect revoked/expired tokens.

        Returns:
            True to continue processing, False to close connection.
        """
        # Use mixin method for JWT revalidation
        if not await self.revalidate_jwt_if_needed():
            logger.warning(
                "JWT revalidation failed",
                identifier=self.context.identifier if self.context else "unknown",
            )
            await self.websocket.close(
                code=WSCloseCode.AUTH_FAILED,
                reason="Token expired or revoked",
            )
            return False
        return True
