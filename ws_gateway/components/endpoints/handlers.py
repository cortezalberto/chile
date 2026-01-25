"""
Concrete WebSocket Endpoint Implementations.

HIGH-03 FIX: Migrated endpoint logic from main.py to reusable classes.
Eliminates ~300 lines of duplicated code across waiter, kitchen, admin, diner endpoints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, WebSocket

from ws_gateway.components.core.constants import WSCloseCode, MSG_REFRESH_SECTORS
from ws_gateway.components.core.context import WebSocketContext, sanitize_log_data
from ws_gateway.components.endpoints.base import JWTWebSocketEndpoint, WebSocketEndpointBase
from ws_gateway.components.data.sector_repository import get_waiter_sector_ids

if TYPE_CHECKING:
    from ws_gateway.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class WaiterEndpoint(JWTWebSocketEndpoint):
    """
    WebSocket endpoint for waiters.

    Features:
    - JWT authentication with WAITER/MANAGER/ADMIN roles
    - Sector-based event filtering
    - refresh_sectors command support
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: "ConnectionManager",
        token: str,
    ):
        super().__init__(
            websocket=websocket,
            manager=manager,
            endpoint_name="/ws/waiter",
            token=token,
            required_roles=["WAITER", "MANAGER", "ADMIN"],
        )
        self._user_id: int = 0
        # HIGH-AUD-02 FIX: Use int | None to distinguish "no tenant" from "tenant 0"
        self._tenant_id: int | None = None
        self._branch_ids: list[int] = []
        self._sector_ids: list[int] = []
        self._is_admin_or_manager: bool = False

    async def create_context(self, auth_data: dict[str, Any]) -> WebSocketContext:
        """Create context with sector information."""
        self._user_id = int(auth_data["sub"])
        # HIGH-AUD-02 FIX: Use None for missing tenant_id instead of 0
        raw_tenant_id = auth_data.get("tenant_id")
        self._tenant_id = int(raw_tenant_id) if raw_tenant_id is not None else None
        self._branch_ids = list(auth_data.get("branch_ids", []))
        roles = auth_data.get("roles", [])

        # Get sector assignments for waiters
        # HIGH-AUD-02 FIX: Only fetch sectors if tenant_id is valid
        if "WAITER" in roles and self._tenant_id is not None:
            self._sector_ids = await get_waiter_sector_ids(self._user_id, self._tenant_id)

        self._is_admin_or_manager = any(role in roles for role in ["MANAGER", "ADMIN"])

        return WebSocketContext.from_jwt_claims(
            self.websocket,
            auth_data,
            self.endpoint_name,
            sector_ids=self._sector_ids,
            is_admin=self._is_admin_or_manager,
        )

    async def register_connection(self, context: WebSocketContext) -> None:
        """Register with sectors for targeted notifications."""
        # CRIT-NEW-03 FIX: Pass tenant_id for multi-tenant isolation
        await self.manager.connect(
            self.websocket,
            self._user_id,
            self._branch_ids,
            self._sector_ids,
            is_admin=self._is_admin_or_manager,
            tenant_id=self._tenant_id,
        )

    async def unregister_connection(self, context: WebSocketContext) -> None:
        """Unregister from connection manager."""
        await self.manager.disconnect(self.websocket)

    async def handle_message(self, data: str) -> None:
        """Handle refresh_sectors command."""
        if data == MSG_REFRESH_SECTORS:
            # Revalidate JWT first
            if not await self.revalidate_jwt(self.token):
                logger.warning("Token validation failed on refresh_sectors", user_id=self._user_id)
                await self.websocket.close(
                    code=WSCloseCode.AUTH_FAILED,
                    reason="Token expired or revoked",
                )
                return

            # Refresh sector assignments
            # HIGH-AUD-02 FIX: Only refresh if tenant_id is valid
            if self._tenant_id is None:
                logger.warning("Cannot refresh sectors without tenant_id", user_id=self._user_id)
                return
            new_sector_ids = await get_waiter_sector_ids(self._user_id, self._tenant_id)
            await self.manager.update_sectors(self.websocket, new_sector_ids)

            try:
                await self.websocket.send_text(f"sectors_updated:{','.join(map(str, new_sector_ids))}")
            except Exception as e:
                logger.warning("Failed to send sectors_updated", user_id=self._user_id, error=str(e))
                return

            logger.info("Waiter sectors refreshed", user_id=self._user_id, sectors=new_sector_ids)
            self._sector_ids = new_sector_ids
        else:
            logger.debug(
                "Unknown message from waiter",
                user_id=self._user_id,
                message=sanitize_log_data(data),
            )


class KitchenEndpoint(JWTWebSocketEndpoint):
    """
    WebSocket endpoint for kitchen staff.

    Features:
    - JWT authentication with KITCHEN/MANAGER/ADMIN roles
    - Receives round events for order preparation
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: "ConnectionManager",
        token: str,
    ):
        super().__init__(
            websocket=websocket,
            manager=manager,
            endpoint_name="/ws/kitchen",
            token=token,
            required_roles=["KITCHEN", "MANAGER", "ADMIN"],
        )
        self._user_id: int = 0
        # HIGH-AUD-02 FIX: Use int | None to distinguish "no tenant" from "tenant 0"
        self._tenant_id: int | None = None
        self._branch_ids: list[int] = []
        self._is_admin_or_manager: bool = False

    async def create_context(self, auth_data: dict[str, Any]) -> WebSocketContext:
        """Create context for kitchen staff."""
        self._user_id = int(auth_data["sub"])
        # HIGH-AUD-02 FIX: Use None for missing tenant_id instead of 0
        raw_tenant_id = auth_data.get("tenant_id")
        self._tenant_id = int(raw_tenant_id) if raw_tenant_id is not None else None
        self._branch_ids = list(auth_data.get("branch_ids", []))
        roles = auth_data.get("roles", [])
        self._is_admin_or_manager = any(role in roles for role in ["MANAGER", "ADMIN"])

        return WebSocketContext.from_jwt_claims(
            self.websocket,
            auth_data,
            self.endpoint_name,
            is_admin=self._is_admin_or_manager,
        )

    async def register_connection(self, context: WebSocketContext) -> None:
        """Register kitchen connection."""
        # CRIT-NEW-03 FIX: Pass tenant_id for multi-tenant isolation
        await self.manager.connect(
            self.websocket,
            self._user_id,
            self._branch_ids,
            is_admin=self._is_admin_or_manager,
            tenant_id=self._tenant_id,
        )

    async def unregister_connection(self, context: WebSocketContext) -> None:
        """Unregister from connection manager."""
        await self.manager.disconnect(self.websocket)

    async def handle_message(self, data: str) -> None:
        """Log unknown messages from kitchen."""
        logger.debug(
            "Unknown message from kitchen",
            user_id=self._user_id,
            message=sanitize_log_data(data),
        )


class AdminEndpoint(JWTWebSocketEndpoint):
    """
    WebSocket endpoint for Dashboard/admin monitoring.

    Features:
    - JWT authentication with MANAGER/ADMIN roles only
    - Receives all branch events for monitoring
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: "ConnectionManager",
        token: str,
    ):
        super().__init__(
            websocket=websocket,
            manager=manager,
            endpoint_name="/ws/admin",
            token=token,
            required_roles=["MANAGER", "ADMIN"],
        )
        self._user_id: int = 0
        # HIGH-AUD-02 FIX: Use int | None to distinguish "no tenant" from "tenant 0"
        self._tenant_id: int | None = None
        self._branch_ids: list[int] = []

    async def create_context(self, auth_data: dict[str, Any]) -> WebSocketContext:
        """Create context for admin."""
        self._user_id = int(auth_data["sub"])
        # HIGH-AUD-02 FIX: Use None for missing tenant_id instead of 0
        raw_tenant_id = auth_data.get("tenant_id")
        self._tenant_id = int(raw_tenant_id) if raw_tenant_id is not None else None
        self._branch_ids = list(auth_data.get("branch_ids", []))

        return WebSocketContext.from_jwt_claims(
            self.websocket,
            auth_data,
            self.endpoint_name,
            is_admin=True,
        )

    async def register_connection(self, context: WebSocketContext) -> None:
        """Register admin connection with full branch access."""
        # CRIT-NEW-03 FIX: Pass tenant_id for multi-tenant isolation
        await self.manager.connect(
            self.websocket,
            self._user_id,
            self._branch_ids,
            is_admin=True,
            tenant_id=self._tenant_id,
        )

    async def unregister_connection(self, context: WebSocketContext) -> None:
        """Unregister from connection manager."""
        await self.manager.disconnect(self.websocket)

    async def handle_message(self, data: str) -> None:
        """Log unknown messages from admin."""
        logger.debug(
            "Unknown message from admin",
            user_id=self._user_id,
            message=sanitize_log_data(data),
        )


class DinerEndpoint(WebSocketEndpointBase):
    """
    WebSocket endpoint for diners at a table.

    Features:
    - Table token authentication (not JWT)
    - Session-based event routing
    - No JWT revalidation (table tokens don't expire mid-session)
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: "ConnectionManager",
        table_token: str,
    ):
        super().__init__(
            websocket=websocket,
            manager=manager,
            endpoint_name="/ws/diner",
        )
        self.table_token = table_token
        self._session_id: int = 0
        self._table_id: int = 0
        self._branch_id: int = 0
        # HIGH-AUD-02 FIX: Use int | None to distinguish "no tenant" from "tenant 0"
        self._tenant_id: int | None = None
        self._pseudo_user_id: int = 0

    async def validate_auth(self) -> dict[str, Any] | None:
        """Validate table token."""
        from shared.security.auth import verify_table_token
        from shared.config.logging import audit_ws_connection

        # Validate origin
        if not self._validate_origin():
            logger.warning(
                "WebSocket connection rejected - invalid origin",
                origin=self.websocket.headers.get("origin"),
            )
            await self.websocket.close(
                code=WSCloseCode.FORBIDDEN,
                reason="Origin not allowed",
            )
            return None

        try:
            token_data = verify_table_token(self.table_token)
            return token_data
        except HTTPException as e:
            logger.warning(
                "WebSocket table token validation failed",
                error=str(e.detail),
            )
            audit_ws_connection(
                event_type="AUTH_FAILED",
                endpoint=self.endpoint_name,
                origin=self.websocket.headers.get("origin"),
                reason="table_token_validation_failed",
            )
            await self.websocket.close(
                code=WSCloseCode.AUTH_FAILED,
                reason="Authentication failed",
            )
            return None

    def _validate_origin(self) -> bool:
        """
        Validate WebSocket origin header.

        HIGH-NEW-03 FIX: Uses shared validate_websocket_origin() function
        to eliminate code duplication across endpoints.
        """
        from shared.config.settings import settings
        from ws_gateway.components.core.constants import validate_websocket_origin

        origin = self.websocket.headers.get("origin")
        return validate_websocket_origin(origin, settings)

    async def create_context(self, auth_data: dict[str, Any]) -> WebSocketContext:
        """Create context from table token."""
        self._session_id = auth_data["session_id"]
        self._table_id = auth_data["table_id"]
        self._branch_id = auth_data["branch_id"]
        # HIGH-AUD-02 FIX: Use None for missing tenant_id instead of 0
        raw_tenant_id = auth_data.get("tenant_id")
        self._tenant_id = int(raw_tenant_id) if raw_tenant_id is not None else None
        self._pseudo_user_id = -self._session_id  # Negative to avoid user ID collision

        return WebSocketContext.from_table_token(
            self.websocket,
            auth_data,
            self.endpoint_name,
        )

    async def register_connection(self, context: WebSocketContext) -> None:
        """Register diner connection and session."""
        # CRIT-NEW-03 FIX: Pass tenant_id for multi-tenant isolation
        await self.manager.connect(
            self.websocket,
            self._pseudo_user_id,
            [self._branch_id],
            tenant_id=self._tenant_id,
        )
        await self.manager.register_session(self.websocket, self._session_id)

    async def unregister_connection(self, context: WebSocketContext) -> None:
        """Unregister session and connection."""
        await self.manager.unregister_session(self.websocket, self._session_id)
        await self.manager.disconnect(self.websocket)

    async def handle_message(self, data: str) -> None:
        """Log unknown messages from diner."""
        logger.debug(
            "Unknown message from diner",
            session_id=self._session_id,
            message=sanitize_log_data(data),
        )
