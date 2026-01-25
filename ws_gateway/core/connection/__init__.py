"""
Connection Management Module.

Modular components extracted from ConnectionManager:
- lifecycle.py: Connection accept/disconnect
- broadcaster.py: Message broadcasting
- cleanup.py: Stale/dead connection cleanup
- stats.py: Statistics aggregation

ARCH-MODULAR: Each component has single responsibility for maintainability.
"""

from ws_gateway.core.connection.lifecycle import ConnectionLifecycle
from ws_gateway.core.connection.broadcaster import ConnectionBroadcaster, is_ws_connected
from ws_gateway.core.connection.cleanup import ConnectionCleanup
from ws_gateway.core.connection.stats import ConnectionStats

__all__ = [
    "ConnectionLifecycle",
    "ConnectionBroadcaster",
    "ConnectionCleanup",
    "ConnectionStats",
    "is_ws_connected",
]
