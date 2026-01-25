"""
Event Routing Helpers.

REDIS-MED-06 FIX: Centralized routing logic for event publishing.
Provides convenience functions for publishing to specific channels.
"""

from __future__ import annotations

import redis.asyncio as redis

from .event_schema import Event
from .publisher import publish_event
from .channels import (
    channel_branch_waiters,
    channel_branch_kitchen,
    channel_sector_waiters,
    channel_table_session,
    channel_branch_admin,
    channel_tenant_admin,
)


async def _publish_with_routing(
    redis_client: redis.Redis,
    event: Event,
    branch_id: int,
    sector_id: int | None,
    to_session: bool = False,
    session_id: int | None = None,
    to_kitchen: bool = False,
    to_admin: bool = True,
) -> None:
    """
    REDIS-MED-06 FIX: Centralized routing logic for event publishing.

    Publishes to appropriate channels based on routing configuration.

    Args:
        redis_client: Async Redis client.
        event: Event to publish.
        branch_id: Branch ID.
        sector_id: If provided, publishes to sector channel.
        to_session: If True, publishes to session channel.
        session_id: Session ID for session channel.
        to_kitchen: If True, publishes to kitchen channel.
        to_admin: If True, publishes to admin channel (default True).
    """
    # Publish to waiters - by sector if available, otherwise by branch
    if sector_id:
        await publish_to_sector(redis_client, sector_id, event)
    else:
        await publish_to_waiters(redis_client, branch_id, event)

    # Publish to kitchen if requested
    if to_kitchen:
        await publish_to_kitchen(redis_client, branch_id, event)

    # Publish to admin channel (usually always)
    if to_admin:
        await publish_to_admin(redis_client, branch_id, event)

    # Publish to session channel for diner notifications
    if to_session and session_id:
        await publish_to_session(redis_client, session_id, event)


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
