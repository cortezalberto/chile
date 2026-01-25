"""
Event Schema.

Defines the unified Event dataclass for all system events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Event:
    """
    Unified event schema for all system events.

    All events follow this structure for consistency and easy parsing.
    The 'entity' field contains event-specific data (IDs, etc.).
    The 'actor' field identifies who triggered the event.

    SHARED-HIGH-06 FIX: Added __post_init__ validation for required fields.
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

    def __post_init__(self) -> None:
        """
        SHARED-HIGH-06 FIX: Validate event fields after initialization.
        Prevents malformed events from being published to Redis.
        """
        # Validate required string fields
        if not self.type or not isinstance(self.type, str):
            raise ValueError("Event type must be a non-empty string")

        # Validate required integer fields
        if not isinstance(self.tenant_id, int) or self.tenant_id <= 0:
            raise ValueError("Event tenant_id must be a positive integer")

        # REDIS-MED-08 FIX: branch_id=0 is valid for tenant-wide entities
        if not isinstance(self.branch_id, int) or self.branch_id < 0:
            raise ValueError("Event branch_id must be a non-negative integer (0 for tenant-wide)")

        # Validate optional integer fields
        if self.table_id is not None and (not isinstance(self.table_id, int) or self.table_id <= 0):
            raise ValueError("Event table_id must be a positive integer or None")

        if self.session_id is not None and (not isinstance(self.session_id, int) or self.session_id <= 0):
            raise ValueError("Event session_id must be a positive integer or None")

        if self.sector_id is not None and (not isinstance(self.sector_id, int) or self.sector_id <= 0):
            raise ValueError("Event sector_id must be a positive integer or None")

        # Validate dict fields
        if self.entity is not None and not isinstance(self.entity, dict):
            raise ValueError("Event entity must be a dict or None")

        if self.actor is not None and not isinstance(self.actor, dict):
            raise ValueError("Event actor must be a dict or None")

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        data = asdict(self)
        data["entity"] = data["entity"] or {}
        data["actor"] = data["actor"] or {}
        data["ts"] = data["ts"] or datetime.now(timezone.utc).isoformat()
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """
        Deserialize event from JSON string.

        SHARED-HIGH-06 FIX: Validation occurs automatically in __post_init__.
        """
        data = json.loads(json_str)
        return cls(**data)
