"""
Event Router - Routes WebSocket events to appropriate connections.

ARCH-AUDIT-03: Extracted from main.py to follow Single Responsibility Principle.
Separates event validation from routing logic.

Usage:
    router = EventRouter(connection_manager)
    sent_count = await router.route_event(event_dict)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ConnectionManagerProtocol(Protocol):
    """Protocol for ConnectionManager to avoid circular imports."""

    async def send_to_admins(
        self, branch_id: int, event: dict, tenant_id: int | None = None
    ) -> int: ...

    async def send_to_sector(
        self, sector_id: int, event: dict, tenant_id: int | None = None
    ) -> int: ...

    async def send_to_waiters_only(
        self, branch_id: int, event: dict, tenant_id: int | None = None
    ) -> int: ...

    async def send_to_session(
        self, session_id: int, event: dict, tenant_id: int | None = None
    ) -> int: ...

    async def send_to_branch(
        self, branch_id: int, event: dict, tenant_id: int | None = None
    ) -> int: ...

    async def send_to_kitchen(
        self, branch_id: int, event: dict, tenant_id: int | None = None
    ) -> int: ...



@dataclass
class RoutingResult:
    """Result of routing an event."""

    admin_sent: int = 0
    waiter_sent: int = 0
    kitchen_sent: int = 0
    diner_sent: int = 0
    errors: list[str] | None = None

    @property
    def total_sent(self) -> int:
        """Total number of clients that received the event."""
        return self.admin_sent + self.waiter_sent + self.kitchen_sent + self.diner_sent

    @property
    def success(self) -> bool:
        """Whether routing completed without errors."""
        return not self.errors


def safe_int(value, field_name: str) -> int | None:
    """
    Convert to int safely, return None if invalid.

    HIGH-WS-02 FIX: Extracted helper function for safe integer conversion.

    Args:
        value: Value to convert
        field_name: Field name for logging

    Returns:
        Integer value or None if invalid
    """
    if value is None:
        return None
    try:
        result = int(value)
        if result <= 0:
            logger.warning(f"Invalid {field_name}: must be positive", value=value)
            return None
        return result
    except (ValueError, TypeError):
        logger.warning(f"Invalid {field_name}: cannot convert to int", value=value)
        return None


class EventRouter:
    """
    Routes events to appropriate WebSocket connections.

    Routing rules:
    - tenant_id: Filter all routes by tenant for multi-tenant isolation
    - branch_id: Send to admins and waiters in branch
    - sector_id: Target specific sector's waiters (if present)
    - session_id: Send to diners at the table
    - to_kitchen: Flag to also send to kitchen staff

    Event types and their routing (from event_types.py):
    - ROUND_PENDING: admins + ALL branch waiters (bypasses sector filter)
    - ROUND_SUBMITTED: admins + waiters (NO kitchen)
    - ROUND_IN_KITCHEN: admins + waiters + kitchen + session
    - ROUND_READY: admins + waiters + kitchen + session
    - ROUND_SERVED: admins + waiters + session
    - TABLE_SESSION_STARTED: admins + ALL branch waiters + session
    - SERVICE_CALL_*: admins + waiters (sector targeted)
    - PAYMENT_*: admins + session
    - TABLE_*: admins + session
    - ENTITY_*: admins only (CRUD events)
    """

    # Events that should also go to kitchen
    KITCHEN_EVENTS = frozenset({
        "ROUND_IN_KITCHEN",
        "ROUND_READY",
        "ROUND_SERVED",
        "TICKET_IN_PROGRESS",
        "TICKET_READY",
        "TICKET_DELIVERED",
    })

    # Events that should go to diners in session
    SESSION_EVENTS = frozenset({
        "ROUND_IN_KITCHEN",
        "ROUND_READY",
        "ROUND_SERVED",
        "ROUND_CANCELED",
        "CHECK_REQUESTED",
        "CHECK_PAID",
        "PAYMENT_APPROVED",
        "PAYMENT_REJECTED",
        "PAYMENT_FAILED",
        "TABLE_SESSION_STARTED",
        "TABLE_CLEARED",
        "TABLE_STATUS_CHANGED",
    })

    # Events that skip waiters (admin-only CRUD events)
    ADMIN_ONLY_EVENTS = frozenset({
        "ENTITY_CREATED",
        "ENTITY_UPDATED",
        "ENTITY_DELETED",
        "CASCADE_DELETE",
    })

    # Events that should go to ALL branch waiters (bypass sector filtering)
    # These are high-priority notifications that all waiters need to see
    BRANCH_WIDE_WAITER_EVENTS = frozenset({
        "ROUND_PENDING",  # New order - all assigned waiters should be aware
        "TABLE_SESSION_STARTED",  # New session - waiters need to know
    })

    def __init__(self, manager: ConnectionManagerProtocol):
        """
        Initialize event router.

        Args:
            manager: ConnectionManager instance for sending events
        """
        self._manager = manager

    async def route_event(self, event: dict) -> RoutingResult:
        """
        Route an event to appropriate connections.

        Args:
            event: Event dictionary with type, tenant_id, branch_id, etc.

        Returns:
            RoutingResult with counts of clients reached
        """
        result = RoutingResult()
        errors: list[str] = []

        try:
            event_type = event.get("type")
            if not event_type:
                errors.append("Event missing 'type' field")
                result.errors = errors
                return result

            # Extract and validate IDs
            tenant_id = safe_int(event.get("tenant_id"), "tenant_id")
            branch_id = safe_int(event.get("branch_id"), "branch_id")
            session_id = safe_int(event.get("session_id"), "session_id")
            sector_id = safe_int(event.get("sector_id"), "sector_id")

            # Determine routing based on event type
            to_kitchen = event_type in self.KITCHEN_EVENTS
            to_session = event_type in self.SESSION_EVENTS
            admin_only = event_type in self.ADMIN_ONLY_EVENTS

            # Branch-level routing
            if branch_id is not None:
                # Always send to admins/managers
                try:
                    result.admin_sent = await self._manager.send_to_admins(
                        branch_id, event, tenant_id=tenant_id
                    )
                    if result.admin_sent > 0:
                        logger.debug(
                            "Dispatched event to admins",
                            event_type=event_type,
                            branch_id=branch_id,
                            tenant_id=tenant_id,
                            clients=result.admin_sent,
                        )
                except Exception as e:
                    errors.append(f"Failed to send to admins: {e}")
                    logger.error("Error sending to admins", error=str(e))

                # Waiter routing (unless admin-only event)
                if not admin_only:
                    try:
                        # Check if this event should go to ALL waiters in branch
                        # (bypass sector filtering for high-priority notifications)
                        branch_wide = event_type in self.BRANCH_WIDE_WAITER_EVENTS

                        if branch_wide:
                            # Always send to all branch waiters for high-priority events
                            result.waiter_sent = await self._manager.send_to_waiters_only(
                                branch_id, event, tenant_id=tenant_id
                            )
                            if result.waiter_sent > 0:
                                logger.debug(
                                    "Dispatched event to all branch waiters (high priority)",
                                    event_type=event_type,
                                    branch_id=branch_id,
                                    tenant_id=tenant_id,
                                    clients=result.waiter_sent,
                                )
                        elif sector_id is not None:
                            # Sector-targeted waiter notification
                            result.waiter_sent = await self._manager.send_to_sector(
                                sector_id, event, tenant_id=tenant_id
                            )
                            if result.waiter_sent > 0:
                                logger.debug(
                                    "Dispatched event to sector waiters",
                                    event_type=event_type,
                                    sector_id=sector_id,
                                    tenant_id=tenant_id,
                                    clients=result.waiter_sent,
                                )
                        else:
                            # Fallback to all waiters in branch
                            result.waiter_sent = await self._manager.send_to_waiters_only(
                                branch_id, event, tenant_id=tenant_id
                            )
                            if result.waiter_sent > 0:
                                logger.debug(
                                    "Dispatched event to all branch waiters",
                                    event_type=event_type,
                                    branch_id=branch_id,
                                    tenant_id=tenant_id,
                                    clients=result.waiter_sent,
                                )
                    except Exception as e:
                        errors.append(f"Failed to send to waiters: {e}")
                        logger.error("Error sending to waiters", error=str(e))

                # Kitchen routing: use send_to_kitchen
                if to_kitchen:
                    try:
                        # Kitchen events go to kitchen connections
                        result.kitchen_sent = await self._manager.send_to_kitchen(
                            branch_id, event, tenant_id=tenant_id
                        )

                        if result.kitchen_sent > 0:
                            logger.debug(
                                "Dispatched event to branch (kitchen)",
                                event_type=event_type,
                                branch_id=branch_id,
                                tenant_id=tenant_id,
                                clients=result.kitchen_sent,
                            )
                    except Exception as e:
                        errors.append(f"Failed to send to branch (kitchen): {e}")
                        logger.error("Error sending to branch", error=str(e))

            # Session-level routing (diners)
            if to_session and session_id is not None:
                try:
                    result.diner_sent = await self._manager.send_to_session(
                        session_id, event, tenant_id=tenant_id
                    )
                    if result.diner_sent > 0:
                        logger.debug(
                            "Dispatched event to session",
                            event_type=event_type,
                            session_id=session_id,
                            tenant_id=tenant_id,
                            diners=result.diner_sent,
                        )
                except Exception as e:
                    errors.append(f"Failed to send to session: {e}")
                    logger.error("Error sending to session", error=str(e))

            if errors:
                result.errors = errors

        except Exception as e:
            logger.error(
                "Error routing event",
                event_type=event.get("type"),
                error=str(e),
                exc_info=True,
            )
            result.errors = [f"Routing error: {e}"]

        return result

    async def route_to_branch(
        self,
        branch_id: int,
        event: dict,
        *,
        tenant_id: int | None = None,
        include_waiters: bool = True,
        include_kitchen: bool = False,
    ) -> RoutingResult:
        """
        Route event to a specific branch with explicit options.

        Args:
            branch_id: Target branch
            event: Event dictionary
            tenant_id: Tenant for isolation
            include_waiters: Send to waiters
            include_kitchen: Send to kitchen

        Returns:
            RoutingResult
        """
        result = RoutingResult()

        result.admin_sent = await self._manager.send_to_admins(
            branch_id, event, tenant_id=tenant_id
        )

        if include_waiters:
            event_type = event.get("type", "")
            branch_wide = event_type in self.BRANCH_WIDE_WAITER_EVENTS
            sector_id = safe_int(event.get("sector_id"), "sector_id")

            if branch_wide or not sector_id:
                # High-priority events or no sector: send to all branch waiters
                result.waiter_sent = await self._manager.send_to_waiters_only(
                    branch_id, event, tenant_id=tenant_id
                )
            else:
                result.waiter_sent = await self._manager.send_to_sector(
                    sector_id, event, tenant_id=tenant_id
                )

        if include_kitchen:
            result.kitchen_sent = await self._manager.send_to_kitchen(
                branch_id, event, tenant_id=tenant_id
            )


        return result

    async def route_to_session(
        self,
        session_id: int,
        event: dict,
        *,
        tenant_id: int | None = None,
    ) -> int:
        """
        Route event to a specific session (diners).

        Args:
            session_id: Target session
            event: Event dictionary
            tenant_id: Tenant for isolation

        Returns:
            Number of diners reached
        """
        return await self._manager.send_to_session(
            session_id, event, tenant_id=tenant_id
        )
