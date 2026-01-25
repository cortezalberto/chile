"""
Redis Subscriber Module.

Modular components extracted from redis_subscriber.py:
- drop_tracker.py: Event drop rate tracking
- validator.py: Event schema validation
- processor.py: Event batch processing

ARCH-MODULAR: Each component has single responsibility for maintainability.
"""

from ws_gateway.core.subscriber.drop_tracker import (
    EventDropRateTracker,
    get_drop_tracker,
    reset_drop_tracker,
)
from ws_gateway.core.subscriber.validator import (
    validate_event_schema,
    validate_event_schema_pure,
    track_unknown_event_type,
    get_unknown_event_metrics,
    reset_unknown_event_tracker,
)
from ws_gateway.core.subscriber.processor import (
    process_event_batch,
    handle_incoming_message,
)

__all__ = [
    # Drop tracker
    "EventDropRateTracker",
    "get_drop_tracker",
    "reset_drop_tracker",
    # Validator
    "validate_event_schema",
    "validate_event_schema_pure",
    "track_unknown_event_type",
    "get_unknown_event_metrics",
    "reset_unknown_event_tracker",
    # Processor
    "process_event_batch",
    "handle_incoming_message",
]
