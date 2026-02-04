"""
Event Services - Real-time event publishing for admin sync.

Provides:
- Admin CRUD event publishing for Dashboard real-time sync
- Typed DomainEvent API for new code
- EventPublisher singleton for publishing
- OUTBOX-PATTERN: Transactional outbox for guaranteed delivery
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

from .outbox_service import (
    write_outbox_event,
    write_billing_outbox_event,
    write_round_outbox_event,
    write_service_call_outbox_event,
)

from .outbox_processor import (
    OutboxProcessor,
    get_outbox_processor,
    start_outbox_processor,
    stop_outbox_processor,
    process_pending_events_once,
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
    # OUTBOX-PATTERN: Transactional outbox for guaranteed delivery
    "write_outbox_event",
    "write_billing_outbox_event",
    "write_round_outbox_event",
    "write_service_call_outbox_event",
    "OutboxProcessor",
    "get_outbox_processor",
    "start_outbox_processor",
    "stop_outbox_processor",
    "process_pending_events_once",
]
