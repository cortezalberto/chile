"""
Event Services - Real-time event publishing for admin sync.

Provides:
- Admin CRUD event publishing for Dashboard real-time sync
- Typed DomainEvent API for new code
- EventPublisher singleton for publishing
"""

from .admin_events import (
    publish_entity_created,
    publish_entity_updated,
    publish_entity_deleted,
    publish_cascade_delete,
)

from .domain_event import (
    DomainEvent,
    EventType,
)

from .publisher import (
    EventPublisher,
    get_event_publisher,
    publish_event_sync,
    publish_event_async,
)

__all__ = [
    # Legacy functions (still widely used)
    "publish_entity_created",
    "publish_entity_updated",
    "publish_entity_deleted",
    "publish_cascade_delete",
    # Typed event API (preferred for new code)
    "DomainEvent",
    "EventType",
    "EventPublisher",
    "get_event_publisher",
    "publish_event_sync",
    "publish_event_async",
]
