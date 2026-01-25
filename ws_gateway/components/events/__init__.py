"""
Event handling components.

Event types, validation, and routing.
"""

from ws_gateway.components.events.types import (
    WebSocketEvent,
    EventType,
    VALID_EVENT_TYPES,
    REQUIRED_EVENT_FIELDS,
    OPTIONAL_EVENT_FIELDS,
)
from ws_gateway.components.events.router import (
    EventRouter,
    RoutingResult,
    safe_int,
)

__all__ = [
    # Event types
    "WebSocketEvent",
    "EventType",
    "VALID_EVENT_TYPES",
    "REQUIRED_EVENT_FIELDS",
    "OPTIONAL_EVENT_FIELDS",
    # Event router
    "EventRouter",
    "RoutingResult",
    "safe_int",
]
