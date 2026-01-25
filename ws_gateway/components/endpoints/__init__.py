"""
WebSocket endpoint components.

Base classes, mixins, and concrete endpoint handlers.
"""

from ws_gateway.components.endpoints.base import (
    WebSocketEndpointBase,
    JWTWebSocketEndpoint,
)
from ws_gateway.components.endpoints.mixins import (
    MessageValidationMixin,
    OriginValidationMixin,
    JWTRevalidationMixin,
    HeartbeatMixin,
    ConnectionLifecycleMixin,
)
from ws_gateway.components.endpoints.handlers import (
    WaiterEndpoint,
    KitchenEndpoint,
    AdminEndpoint,
    DinerEndpoint,
)

__all__ = [
    # Base classes
    "WebSocketEndpointBase",
    "JWTWebSocketEndpoint",
    # Mixins
    "MessageValidationMixin",
    "OriginValidationMixin",
    "JWTRevalidationMixin",
    "HeartbeatMixin",
    "ConnectionLifecycleMixin",
    # Handlers
    "WaiterEndpoint",
    "KitchenEndpoint",
    "AdminEndpoint",
    "DinerEndpoint",
]
