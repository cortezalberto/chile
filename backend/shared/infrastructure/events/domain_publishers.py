"""
Domain-Specific Event Publishing Functions.

High-level functions for publishing domain events (rounds, service calls, etc.).
"""

from __future__ import annotations

import redis.asyncio as redis

from .event_types import (
    ROUND_PENDING,
    ROUND_CONFIRMED,
    ROUND_SUBMITTED,
    ROUND_IN_KITCHEN,
    ROUND_READY,
    ROUND_SERVED,
    SERVICE_CALL_ACKED,
    SERVICE_CALL_CLOSED,
    PAYMENT_APPROVED,
    PAYMENT_REJECTED,
    CHECK_PAID,
)
from .event_schema import Event
from .routing import (
    _publish_with_routing,
    publish_to_sector,
    publish_to_waiters,
    publish_to_admin,
    publish_to_tenant_admin,
)


async def publish_round_event(
    redis_client: redis.Redis,
    event_type: str,
    tenant_id: int,
    branch_id: int,
    table_id: int,
    session_id: int,
    round_id: int,
    round_number: int,
    actor_user_id: int | None = None,
    actor_role: str = "DINER",
    sector_id: int | None = None,
) -> None:
    """
    Convenience function to publish round-related events.

    Publishes to FOUR channels for complete circuit visibility:
    1. Waiters (by sector if available, otherwise by branch)
    2. Kitchen (for order preparation - only for IN_KITCHEN, READY, SERVED)
    3. Admin/Dashboard (for manager monitoring)
    4. Session (for diner notifications - only for IN_KITCHEN, READY, SERVED)

    Args:
        sector_id: If provided, publishes to sector channel instead of branch waiters.
    """
    event = Event(
        type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=table_id,
        session_id=session_id,
        sector_id=sector_id,
        entity={"round_id": round_id, "round_number": round_number},
        actor={"user_id": actor_user_id, "role": actor_role},
    )

    # Determine routing based on event type
    # New flow: PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED
    # Kitchen only sees from SUBMITTED onwards (after admin sends to kitchen)
    # Admin sees all events for monitoring
    # Session (diners) only sees IN_KITCHEN, READY, SERVED
    to_kitchen = event_type in [ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED]
    to_session = event_type in [ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED]
    to_admin = event_type in [ROUND_PENDING, ROUND_CONFIRMED, ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED]

    await _publish_with_routing(
        redis_client=redis_client,
        event=event,
        branch_id=branch_id,
        sector_id=sector_id,
        to_session=to_session,
        session_id=session_id,
        to_kitchen=to_kitchen,
        to_admin=to_admin,
    )


async def publish_service_call_event(
    redis_client: redis.Redis,
    event_type: str,
    tenant_id: int,
    branch_id: int,
    table_id: int,
    session_id: int,
    call_id: int,
    call_type: str,
    actor_user_id: int | None = None,
    actor_role: str = "DINER",
    sector_id: int | None = None,
) -> None:
    """
    Publish service call events (created, acknowledged, closed).

    Publishes to:
    1. Waiters (by sector if available, otherwise by branch)
    2. Admin/Dashboard (for manager monitoring)
    3. Session (for diner acknowledgment notifications - only ACKED, CLOSED)

    Args:
        sector_id: If provided, publishes to sector channel instead of branch waiters.
    """
    event = Event(
        type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=table_id,
        session_id=session_id,
        sector_id=sector_id,
        entity={"call_id": call_id, "call_type": call_type},
        actor={"user_id": actor_user_id, "role": actor_role},
    )

    to_session = event_type in [SERVICE_CALL_ACKED, SERVICE_CALL_CLOSED]

    await _publish_with_routing(
        redis_client=redis_client,
        event=event,
        branch_id=branch_id,
        sector_id=sector_id,
        to_session=to_session,
        session_id=session_id,
        to_kitchen=False,
        to_admin=True,
    )


async def publish_check_event(
    redis_client: redis.Redis,
    event_type: str,
    tenant_id: int,
    branch_id: int,
    table_id: int,
    session_id: int,
    check_id: int,
    total_cents: int,
    paid_cents: int = 0,
    actor_user_id: int | None = None,
    actor_role: str = "DINER",
    sector_id: int | None = None,
) -> None:
    """
    Publish billing/check events.

    Publishes to:
    1. Waiters (by sector if available, otherwise by branch)
    2. Admin/Dashboard (for manager monitoring)
    3. Session (for diner payment notifications - APPROVED, REJECTED, PAID)

    Args:
        sector_id: If provided, publishes to sector channel instead of branch waiters.
    """
    event = Event(
        type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=table_id,
        session_id=session_id,
        sector_id=sector_id,
        entity={
            "check_id": check_id,
            "total_cents": total_cents,
            "paid_cents": paid_cents,
        },
        actor={"user_id": actor_user_id, "role": actor_role},
    )

    to_session = event_type in [PAYMENT_APPROVED, PAYMENT_REJECTED, CHECK_PAID]

    await _publish_with_routing(
        redis_client=redis_client,
        event=event,
        branch_id=branch_id,
        sector_id=sector_id,
        to_session=to_session,
        session_id=session_id,
        to_kitchen=False,
        to_admin=True,
    )


async def publish_table_event(
    redis_client: redis.Redis,
    event_type: str,
    tenant_id: int,
    branch_id: int,
    table_id: int,
    table_code: str,
    session_id: int | None = None,
    table_status: str | None = None,
    actor_user_id: int | None = None,
    actor_role: str = "WAITER",
    sector_id: int | None = None,
) -> None:
    """
    Publish table session events (started, cleared).

    Publishes to THREE channels for complete visibility:
    1. Waiters (by sector if available, otherwise by branch)
    2. Admin/Dashboard (for manager monitoring)
    3. Also to branch waiters if sector-specific (so all waiters see new tables)

    Args:
        sector_id: If provided, publishes to sector channel AND branch waiters.
        table_status: Optional table status for TABLE_STATUS_CHANGED events.
    """
    entity_data = {"table_code": table_code}
    if table_status:
        entity_data["table_status"] = table_status

    event = Event(
        type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=table_id,
        session_id=session_id,
        sector_id=sector_id,
        entity=entity_data,
        actor={"user_id": actor_user_id, "role": actor_role},
    )

    # For table events, publish to sector AND branch waiters if sector specified
    if sector_id:
        await publish_to_sector(redis_client, sector_id, event)
        await publish_to_waiters(redis_client, branch_id, event)
    else:
        await publish_to_waiters(redis_client, branch_id, event)

    # Always publish to admin for real-time table monitoring
    await publish_to_admin(redis_client, branch_id, event)


async def publish_admin_crud_event(
    redis_client: redis.Redis,
    event_type: str,
    tenant_id: int,
    branch_id: int | None,
    entity_type: str,
    entity_id: int,
    entity_name: str | None = None,
    affected_entities: list[dict] | None = None,
    actor_user_id: int | None = None,
) -> None:
    """
    Publish admin CRUD events for real-time Dashboard sync.

    Args:
        redis_client: Async Redis client.
        event_type: ENTITY_CREATED, ENTITY_UPDATED, ENTITY_DELETED, or CASCADE_DELETE.
        tenant_id: Tenant ID.
        branch_id: Branch ID (None for tenant-wide entities like categories).
        entity_type: Type of entity (e.g., "product", "category", "table", "staff").
        entity_id: ID of the entity.
        entity_name: Optional name of the entity for display.
        affected_entities: For CASCADE_DELETE, list of affected child entities.
        actor_user_id: ID of user who performed the action.
    """
    entity_data = {
        "entity_type": entity_type,
        "entity_id": entity_id,
    }
    if entity_name:
        entity_data["entity_name"] = entity_name
    if affected_entities:
        entity_data["affected_entities"] = affected_entities

    event = Event(
        type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id or 0,  # 0 for tenant-wide entities
        entity=entity_data,
        actor={"user_id": actor_user_id, "role": "ADMIN"},
    )

    # Publish to branch-specific admin channel if branch_id is provided
    if branch_id:
        await publish_to_admin(redis_client, branch_id, event)

    # Always publish to tenant-wide admin channel
    await publish_to_tenant_admin(redis_client, tenant_id, event)
