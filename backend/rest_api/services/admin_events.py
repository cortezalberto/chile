"""
DEF-HIGH-01 FIX: Service for publishing admin CRUD events.
Enables real-time sync between Dashboard users.
"""

import asyncio
from typing import Optional

from shared.events import (
    get_redis_client,
    publish_admin_crud_event,
    ENTITY_CREATED,
    ENTITY_UPDATED,
    ENTITY_DELETED,
    CASCADE_DELETE,
)
from shared.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a task
            asyncio.create_task(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        asyncio.run(coro)


async def _publish_event(
    event_type: str,
    tenant_id: int,
    branch_id: Optional[int],
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    affected_entities: Optional[list[dict]] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    """Internal async function to publish event."""
    redis_client = None
    try:
        redis_client = await get_redis_client()
        await publish_admin_crud_event(
            redis_client=redis_client,
            event_type=event_type,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            affected_entities=affected_entities,
            actor_user_id=actor_user_id,
        )
        logger.info(
            "Admin event published",
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except Exception as e:
        logger.error("Failed to publish admin event", error=str(e))
    finally:
        if redis_client:
            await redis_client.close()


def publish_entity_created(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    """Publish ENTITY_CREATED event."""
    _run_async(
        _publish_event(
            event_type=ENTITY_CREATED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            actor_user_id=actor_user_id,
        )
    )


def publish_entity_updated(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    """Publish ENTITY_UPDATED event."""
    _run_async(
        _publish_event(
            event_type=ENTITY_UPDATED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            actor_user_id=actor_user_id,
        )
    )


def publish_entity_deleted(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    """Publish ENTITY_DELETED event."""
    _run_async(
        _publish_event(
            event_type=ENTITY_DELETED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            actor_user_id=actor_user_id,
        )
    )


def publish_cascade_delete(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    affected_entities: Optional[list[dict]] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    """
    Publish CASCADE_DELETE event with affected child entities.

    Args:
        affected_entities: List of dicts with {"type": str, "id": int, "name": str}
    """
    _run_async(
        _publish_event(
            event_type=CASCADE_DELETE,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            affected_entities=affected_entities,
            actor_user_id=actor_user_id,
        )
    )
