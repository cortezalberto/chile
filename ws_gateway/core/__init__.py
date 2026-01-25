"""
WebSocket Gateway Core Module.

Modular components for connection and subscriber management:
- connection/: Connection lifecycle, broadcasting, cleanup, stats
- subscriber/: Redis event processing (drop tracking, validation, processing)

ARCH-MODULAR: Extracted from monolithic files for maintainability.
"""

from ws_gateway.core.connection import (
    ConnectionLifecycle,
    ConnectionBroadcaster,
    ConnectionCleanup,
    ConnectionStats,
    is_ws_connected,
)

from ws_gateway.core.subscriber import (
    EventDropRateTracker,
    get_drop_tracker,
    reset_drop_tracker,
    validate_event_schema,
    validate_event_schema_pure,
    track_unknown_event_type,
    get_unknown_event_metrics,
    reset_unknown_event_tracker,
    process_event_batch,
    handle_incoming_message,
)

__all__ = [
    # Connection module
    "ConnectionLifecycle",
    "ConnectionBroadcaster",
    "ConnectionCleanup",
    "ConnectionStats",
    "is_ws_connected",
    # Subscriber module
    "EventDropRateTracker",
    "get_drop_tracker",
    "reset_drop_tracker",
    "validate_event_schema",
    "validate_event_schema_pure",
    "track_unknown_event_type",
    "get_unknown_event_metrics",
    "reset_unknown_event_tracker",
    "process_event_batch",
    "handle_incoming_message",
]
