"""
DEF-HIGH-01 FIX: Service for publishing admin CRUD events.
Enables real-time sync between Dashboard users.

REDIS-CRIT-02 FIX: Added error handling for fire-and-forget tasks to prevent
silent failures when publishing events.

PERF-BGTASK-01: Standardized to use FastAPI BackgroundTasks in request contexts.
This is the recommended approach for fire-and-forget tasks in FastAPI.
The _run_async fallback is preserved for code running outside request context
(jobs, scripts, CLI tools, etc.).
"""

import asyncio
from typing import Optional, TYPE_CHECKING

from shared.infrastructure.events import (
    get_redis_client,
    publish_admin_crud_event,
    ENTITY_CREATED,
    ENTITY_UPDATED,
    ENTITY_DELETED,
    CASCADE_DELETE,
)
from shared.config.logging import get_logger

# TYPE_CHECKING import to avoid runtime circular dependency
if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = get_logger(__name__)


def _task_error_callback(task: asyncio.Task) -> None:
    """
    REDIS-CRIT-02 FIX: Callback to handle errors from fire-and-forget tasks.

    This ensures that errors from async event publishing are logged
    instead of being silently ignored.
    """
    try:
        exc = task.exception()
        if exc is not None:
            # PERF-DEBUG-01: Include task name for easier debugging
            task_name = task.get_name() if hasattr(task, 'get_name') else 'unknown'
            logger.error(
                "Admin event task failed",
                task_name=task_name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    except asyncio.CancelledError:
        # Task was cancelled, not an error
        pass
    except asyncio.InvalidStateError:
        # Task hasn't completed yet (shouldn't happen in done callback)
        pass


def _run_async(coro, task_name: str = "admin_event"):
    """
    MED-03 FIX: Run an async coroutine from sync code.
    REDIS-CRIT-02 FIX: Added error callback for fire-and-forget tasks.
    PERF-DEBUG-01: Added task_name for debugging.

    Handles three scenarios:
    1. If already in an async context with running loop, creates a task with error callback
    2. If loop exists but not running, uses run_until_complete
    3. If no loop exists, creates one with asyncio.run

    Args:
        coro: The async coroutine to execute
        task_name: Name for the task (for debugging)
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # REDIS-CRIT-02 FIX: Add error callback to capture failures
            # PERF-DEBUG-01: Add task name for debugging
            task = asyncio.create_task(coro, name=task_name)
            task.add_done_callback(_task_error_callback)
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
    """
    MED-03 FIX: Internal async function to publish admin CRUD events via Redis.

    Args:
        event_type: Event type constant (ENTITY_CREATED, ENTITY_UPDATED, etc.)
        tenant_id: Tenant ID for multi-tenant isolation
        branch_id: Optional branch ID for branch-specific events
        entity_type: Type of entity (e.g., "branch", "product", "category")
        entity_id: ID of the affected entity
        entity_name: Optional human-readable name of the entity
        affected_entities: Optional list of child entities affected by cascade delete
        actor_user_id: Optional ID of the user who triggered the action
    """
    try:
        # CRIT-01 FIX: Use pooled connection without closing it
        # The pool manages connection lifecycle - we should NOT close pooled connections
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
    # CRIT-01 FIX: Removed finally block that closed pooled connection


def publish_entity_created(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    background_tasks: Optional["BackgroundTasks"] = None,
) -> None:
    """
    Publish ENTITY_CREATED event.

    PERF-BGTASK-01: Use background_tasks in FastAPI request context for
    proper task lifecycle management. Falls back to _run_async for
    code outside request context (jobs, scripts, etc.).

    Args:
        background_tasks: FastAPI BackgroundTasks dependency (recommended in routes)
    """
    if background_tasks is not None:
        # PERF-BGTASK-01: Use FastAPI's BackgroundTasks for proper lifecycle
        background_tasks.add_task(
            _publish_event,
            event_type=ENTITY_CREATED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            actor_user_id=actor_user_id,
        )
    else:
        # Fallback for code outside request context
        task_name = f"admin_event:CREATED:{entity_type}:{entity_id}"
        _run_async(
            _publish_event(
                event_type=ENTITY_CREATED,
                tenant_id=tenant_id,
                branch_id=branch_id,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                actor_user_id=actor_user_id,
            ),
            task_name=task_name,
        )


def publish_entity_updated(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    background_tasks: Optional["BackgroundTasks"] = None,
) -> None:
    """
    Publish ENTITY_UPDATED event.

    PERF-BGTASK-01: Use background_tasks in FastAPI request context for
    proper task lifecycle management. Falls back to _run_async for
    code outside request context (jobs, scripts, etc.).

    Args:
        background_tasks: FastAPI BackgroundTasks dependency (recommended in routes)
    """
    if background_tasks is not None:
        background_tasks.add_task(
            _publish_event,
            event_type=ENTITY_UPDATED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            actor_user_id=actor_user_id,
        )
    else:
        task_name = f"admin_event:UPDATED:{entity_type}:{entity_id}"
        _run_async(
            _publish_event(
                event_type=ENTITY_UPDATED,
                tenant_id=tenant_id,
                branch_id=branch_id,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                actor_user_id=actor_user_id,
            ),
            task_name=task_name,
        )


def publish_entity_deleted(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    background_tasks: Optional["BackgroundTasks"] = None,
) -> None:
    """
    Publish ENTITY_DELETED event.

    PERF-BGTASK-01: Use background_tasks in FastAPI request context for
    proper task lifecycle management. Falls back to _run_async for
    code outside request context (jobs, scripts, etc.).

    Args:
        background_tasks: FastAPI BackgroundTasks dependency (recommended in routes)
    """
    if background_tasks is not None:
        background_tasks.add_task(
            _publish_event,
            event_type=ENTITY_DELETED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            actor_user_id=actor_user_id,
        )
    else:
        task_name = f"admin_event:DELETED:{entity_type}:{entity_id}"
        _run_async(
            _publish_event(
                event_type=ENTITY_DELETED,
                tenant_id=tenant_id,
                branch_id=branch_id,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                actor_user_id=actor_user_id,
            ),
            task_name=task_name,
        )


def publish_cascade_delete(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: Optional[str] = None,
    affected_entities: Optional[list[dict]] = None,
    branch_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    background_tasks: Optional["BackgroundTasks"] = None,
) -> None:
    """
    Publish CASCADE_DELETE event with affected child entities.

    PERF-BGTASK-01: Use background_tasks in FastAPI request context for
    proper task lifecycle management. Falls back to _run_async for
    code outside request context (jobs, scripts, etc.).

    Args:
        affected_entities: List of dicts with {"type": str, "id": int, "name": str}
        background_tasks: FastAPI BackgroundTasks dependency (recommended in routes)
    """
    if background_tasks is not None:
        background_tasks.add_task(
            _publish_event,
            event_type=CASCADE_DELETE,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            affected_entities=affected_entities,
            actor_user_id=actor_user_id,
        )
    else:
        task_name = f"admin_event:CASCADE_DELETE:{entity_type}:{entity_id}"
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
            ),
            task_name=task_name,
        )
