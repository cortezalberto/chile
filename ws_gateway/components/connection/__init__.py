"""
Connection management components.

Handles connection lifecycle: indices, locks, heartbeat, rate limiting.
"""

from ws_gateway.components.connection.index import ConnectionIndex
from ws_gateway.components.connection.locks import LockManager
from ws_gateway.components.connection.lock_sequence import (
    LockSequence,
    LockOrder,
    DeadlockRiskError,
    with_user_and_branches,
    with_counter_and_user,
)
from ws_gateway.components.connection.heartbeat import HeartbeatTracker
from ws_gateway.components.connection.rate_limiter import WebSocketRateLimiter

__all__ = [
    "ConnectionIndex",
    "LockManager",
    "LockSequence",
    "LockOrder",
    "DeadlockRiskError",
    "with_user_and_branches",
    "with_counter_and_user",
    "HeartbeatTracker",
    "WebSocketRateLimiter",
]
