"""
Event system for real-time notifications via Redis pub/sub.
Defines event schema and publishing utilities.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from shared.settings import REDIS_URL


# =============================================================================
# Event Types
# =============================================================================

# Round lifecycle events
ROUND_SUBMITTED = "ROUND_SUBMITTED"
ROUND_IN_KITCHEN = "ROUND_IN_KITCHEN"
ROUND_READY = "ROUND_READY"
ROUND_SERVED = "ROUND_SERVED"
ROUND_CANCELED = "ROUND_CANCELED"

# Service call events
SERVICE_CALL_CREATED = "SERVICE_CALL_CREATED"
SERVICE_CALL_ACKED = "SERVICE_CALL_ACKED"
SERVICE_CALL_CLOSED = "SERVICE_CALL_CLOSED"

# Billing events
CHECK_REQUESTED = "CHECK_REQUESTED"
PAYMENT_APPROVED = "PAYMENT_APPROVED"
PAYMENT_REJECTED = "PAYMENT_REJECTED"
CHECK_PAID = "CHECK_PAID"

# Table events
TABLE_SESSION_STARTED = "TABLE_SESSION_STARTED"
TABLE_CLEARED = "TABLE_CLEARED"

# DEF-HIGH-01 FIX: Admin CRUD events for real-time sync between Dashboard users
ENTITY_CREATED = "ENTITY_CREATED"
ENTITY_UPDATED = "ENTITY_UPDATED"
ENTITY_DELETED = "ENTITY_DELETED"
CASCADE_DELETE = "CASCADE_DELETE"


# =============================================================================
# Event Schema
# =============================================================================


@dataclass
class Event:
    """
    Unified event schema for all system events.

    All events follow this structure for consistency and easy parsing.
    The 'entity' field contains event-specific data (IDs, etc.).
    The 'actor' field identifies who triggered the event.
    """

    type: str
    tenant_id: int
    branch_id: int
    table_id: int | None = None
    session_id: int | None = None
    sector_id: int | None = None  # For sector-based waiter notifications
    entity: dict[str, Any] = field(default_factory=dict)
    actor: dict[str, Any] = field(default_factory=dict)
    ts: str | None = None
    v: int = 1  # Schema version for future compatibility

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        data = asdict(self)
        data["entity"] = data["entity"] or {}
        data["actor"] = data["actor"] or {}
        data["ts"] = data["ts"] or datetime.now(timezone.utc).isoformat()
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Deserialize event from JSON string."""
        data = json.loads(json_str)
        return cls(**data)


# =============================================================================
# Redis Channel Naming
# =============================================================================


def channel_branch_waiters(branch_id: int) -> str:
    """Channel for waiter notifications in a branch."""
    return f"branch:{branch_id}:waiters"


def channel_branch_kitchen(branch_id: int) -> str:
    """Channel for kitchen notifications in a branch."""
    return f"branch:{branch_id}:kitchen"


def channel_user(user_id: int) -> str:
    """Channel for direct user notifications."""
    return f"user:{user_id}"


def channel_table_session(session_id: int) -> str:
    """Channel for diner notifications on a table session."""
    return f"session:{session_id}"


# Sector channel for waiter assignment-based notifications
def channel_sector_waiters(sector_id: int) -> str:
    """Channel for waiter notifications filtered by sector assignment."""
    return f"sector:{sector_id}:waiters"


# DEF-HIGH-01 FIX: Admin channel for Dashboard real-time sync
def channel_branch_admin(branch_id: int) -> str:
    """Channel for admin/dashboard notifications in a branch."""
    return f"branch:{branch_id}:admin"


def channel_tenant_admin(tenant_id: int) -> str:
    """Channel for tenant-wide admin notifications."""
    return f"tenant:{tenant_id}:admin"


# =============================================================================
# Redis Connection Pool (BACK-HIGH-04)
# =============================================================================

# Global Redis connection pool singleton
_redis_pool: redis.Redis | None = None


async def get_redis_pool() -> redis.Redis:
    """
    Get or create the Redis connection pool singleton.

    Uses a connection pool with max_connections=20 for efficient connection reuse.
    This avoids creating a new connection per request, improving performance
    and reducing connection overhead.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            REDIS_URL,
            max_connections=20,
            decode_responses=True,
            socket_connect_timeout=5,  # Connection timeout
            socket_timeout=5,  # Read/write timeout
        )
    return _redis_pool


async def close_redis_pool() -> None:
    """
    Close the Redis connection pool on application shutdown.

    Should be called during application lifecycle shutdown to cleanly
    release all connections in the pool.
    """
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


async def get_redis_client() -> redis.Redis:
    """
    Get an async Redis client.

    Deprecated: Use get_redis_pool() instead for better connection management.
    This function now returns the pooled connection for backward compatibility.
    """
    return await get_redis_pool()


# =============================================================================
# Event Publishing
# =============================================================================


async def publish_event(
    redis_client: redis.Redis,
    channel: str,
    event: Event,
) -> int:
    """
    Publish an event to a Redis channel.

    Args:
        redis_client: Async Redis client.
        channel: Redis channel name.
        event: Event to publish.

    Returns:
        Number of subscribers that received the message.
    """
    return await redis_client.publish(channel, event.to_json())


async def publish_to_waiters(
    redis_client: redis.Redis,
    branch_id: int,
    event: Event,
) -> int:
    """Convenience function to publish to waiters channel."""
    return await publish_event(
        redis_client,
        channel_branch_waiters(branch_id),
        event,
    )


async def publish_to_kitchen(
    redis_client: redis.Redis,
    branch_id: int,
    event: Event,
) -> int:
    """Convenience function to publish to kitchen channel."""
    return await publish_event(
        redis_client,
        channel_branch_kitchen(branch_id),
        event,
    )


async def publish_to_sector(
    redis_client: redis.Redis,
    sector_id: int,
    event: Event,
) -> int:
    """
    Publish to a specific sector channel for assigned waiters.

    Used when events should only go to waiters assigned to a particular sector.
    """
    return await publish_event(
        redis_client,
        channel_sector_waiters(sector_id),
        event,
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
    2. Kitchen (for order preparation)
    3. Admin/Dashboard (for manager monitoring)
    4. Session (for diner notifications)

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

    # 1. Publish to waiters - by sector if available, otherwise by branch
    if sector_id:
        await publish_to_sector(redis_client, sector_id, event)
    else:
        await publish_to_waiters(redis_client, branch_id, event)

    # 2. Publish to kitchen for relevant events:
    # - ROUND_SUBMITTED: New order to prepare
    # - ROUND_IN_KITCHEN: Confirmation order is being prepared
    # - ROUND_READY: Order ready for pickup (status sync)
    # - ROUND_SERVED: Order delivered (status sync)
    if event_type in [ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED]:
        await publish_to_kitchen(redis_client, branch_id, event)

    # 3. Publish to admin channel for Dashboard/manager monitoring
    # Managers need visibility of all round events for supervision
    if event_type in [ROUND_SUBMITTED, ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED]:
        await publish_to_admin(redis_client, branch_id, event)

    # 4. Publish to session channel for diner notifications
    if event_type in [ROUND_IN_KITCHEN, ROUND_READY, ROUND_SERVED]:
        await publish_to_session(redis_client, session_id, event)


async def publish_to_session(
    redis_client: redis.Redis,
    session_id: int,
    event: Event,
) -> int:
    """Publish to a specific table session channel."""
    return await publish_event(
        redis_client,
        channel_table_session(session_id),
        event,
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
    3. Session (for diner acknowledgment notifications)

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

    # 1. Publish to waiters - by sector if available, otherwise by branch
    if sector_id:
        await publish_to_sector(redis_client, sector_id, event)
    else:
        await publish_to_waiters(redis_client, branch_id, event)

    # 2. Publish to admin channel for Dashboard/manager monitoring
    # SERVICE_CALL_CREATED is important for managers to see customer needs
    await publish_to_admin(redis_client, branch_id, event)

    # 3. Diners need acknowledgment/close notifications
    if event_type in [SERVICE_CALL_ACKED, SERVICE_CALL_CLOSED]:
        await publish_to_session(redis_client, session_id, event)


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
    3. Session (for diner payment notifications)

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

    # 1. Publish to waiters - by sector if available, otherwise by branch
    if sector_id:
        await publish_to_sector(redis_client, sector_id, event)
    else:
        await publish_to_waiters(redis_client, branch_id, event)

    # 2. Publish to admin channel for Dashboard/manager monitoring
    # CHECK_REQUESTED and CHECK_PAID are important for managers
    await publish_to_admin(redis_client, branch_id, event)

    # 3. Diners need payment confirmations
    if event_type in [PAYMENT_APPROVED, PAYMENT_REJECTED, CHECK_PAID]:
        await publish_to_session(redis_client, session_id, event)


async def publish_table_event(
    redis_client: redis.Redis,
    event_type: str,
    tenant_id: int,
    branch_id: int,
    table_id: int,
    table_code: str,
    session_id: int | None = None,
    actor_user_id: int | None = None,
    actor_role: str = "WAITER",
    sector_id: int | None = None,
) -> None:
    """
    Publish table session events (started, cleared).

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
        entity={"table_code": table_code},
        actor={"user_id": actor_user_id, "role": actor_role},
    )

    # Publish to waiters - by sector if available, otherwise by branch
    if sector_id:
        await publish_to_sector(redis_client, sector_id, event)
    else:
        await publish_to_waiters(redis_client, branch_id, event)


# =============================================================================
# DEF-HIGH-01 FIX: Admin CRUD Event Publishing
# =============================================================================


async def publish_to_admin(
    redis_client: redis.Redis,
    branch_id: int,
    event: Event,
) -> int:
    """Publish to admin/dashboard channel for a branch."""
    return await publish_event(
        redis_client,
        channel_branch_admin(branch_id),
        event,
    )


async def publish_to_tenant_admin(
    redis_client: redis.Redis,
    tenant_id: int,
    event: Event,
) -> int:
    """Publish to tenant-wide admin channel."""
    return await publish_event(
        redis_client,
        channel_tenant_admin(tenant_id),
        event,
    )


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
        branch_id=branch_id or 0,
        entity=entity_data,
        actor={"user_id": actor_user_id, "role": "ADMIN"},
    )

    # Publish to branch-specific admin channel if branch_id is provided
    if branch_id:
        await publish_to_admin(redis_client, branch_id, event)

    # Always publish to tenant-wide admin channel
    await publish_to_tenant_admin(redis_client, tenant_id, event)
