"""
Core WebSocket Gateway components.

Foundational components: constants, context, and dependency injection.
"""

from ws_gateway.components.core.constants import WSCloseCode, WSConstants
from ws_gateway.components.core.context import WebSocketContext, sanitize_log_data
from ws_gateway.components.core.dependencies import (
    ConnectionManagerDependencies,
    get_lock_manager,
    get_metrics_collector,
    get_heartbeat_tracker,
    get_rate_limiter,
    reset_singletons,
)

__all__ = [
    # Constants
    "WSCloseCode",
    "WSConstants",
    # Context
    "WebSocketContext",
    "sanitize_log_data",
    # Dependencies
    "ConnectionManagerDependencies",
    "get_lock_manager",
    "get_metrics_collector",
    "get_heartbeat_tracker",
    "get_rate_limiter",
    "reset_singletons",
]
