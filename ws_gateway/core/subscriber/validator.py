"""
Event Validation.

Validates incoming event schema and tracks unknown event types.
Extracted from redis_subscriber.py for better maintainability.

ARCH-MODULAR-06: Single Responsibility - event validation only.
"""

from __future__ import annotations

import logging
from typing import Any

from ws_gateway.components.events.types import (
    WebSocketEvent,
    UnknownEventTypeTracker,
)

logger = logging.getLogger(__name__)

# Global tracker for unknown event types
_unknown_event_tracker = UnknownEventTypeTracker()


def validate_event_schema_pure(
    data: dict[str, Any],
) -> tuple[bool, str | None, WebSocketEvent | None]:
    """
    Pure validation of event schema without side effects.

    This function performs schema validation only, without any
    tracking or logging side effects.

    Args:
        data: Event data dictionary.

    Returns:
        Tuple of (is_valid, error_message, event_object).
        - is_valid: True if schema is valid
        - error_message: Error string if invalid, None if valid
        - event_object: WebSocketEvent if valid, None if invalid
    """
    try:
        event = WebSocketEvent.from_dict(data)
        return True, None, event
    except ValueError as e:
        return False, str(e), None


def track_unknown_event_type(event: WebSocketEvent) -> None:
    """
    Track unknown event types for monitoring.

    This function has a side effect - it updates the global
    unknown event tracker and may log a warning.

    Args:
        event: Validated WebSocketEvent object.
    """
    if not event.is_known_type:
        is_first = _unknown_event_tracker.record(event.event_type)
        if is_first:
            logger.warning(
                "Unknown event type received (first occurrence)",
                event_type=event.event_type,
                total_unknown_count=_unknown_event_tracker.count,
            )


def validate_event_schema(data: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate incoming event schema and track unknown types.

    This function combines validation with tracking side effect.
    For pure validation without tracking, use validate_event_schema_pure().

    Note: This function has a side effect - it tracks unknown event types
    in the global _unknown_event_tracker.

    Args:
        data: Event data dictionary.

    Returns:
        Tuple of (is_valid, error_message).
    """
    is_valid, error, event = validate_event_schema_pure(data)
    if is_valid and event:
        track_unknown_event_type(event)
    return is_valid, error


def get_unknown_event_metrics() -> dict[str, Any]:
    """
    Get metrics about unknown event types.

    Returns:
        Dictionary with unknown event tracking metrics.
    """
    return _unknown_event_tracker.get_metrics()


def reset_unknown_event_tracker() -> None:
    """Reset the unknown event tracker (for testing)."""
    global _unknown_event_tracker
    _unknown_event_tracker = UnknownEventTypeTracker()
