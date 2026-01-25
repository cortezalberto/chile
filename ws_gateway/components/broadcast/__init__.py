"""
Broadcasting components.

Message broadcasting with Strategy pattern and multi-tenant isolation.
"""

from ws_gateway.components.broadcast.router import (
    BroadcastRouter,
    BroadcastStrategy,
    BatchBroadcastStrategy,
    AdaptiveBatchStrategy,
    BroadcastObserver,
    MetricsObserverAdapter,
    create_default_router,
    create_adaptive_router,
)
from ws_gateway.components.broadcast.tenant_filter import (
    TenantFilter,
    TenantAwareBroadcaster,
)

__all__ = [
    # Broadcast router
    "BroadcastRouter",
    "BroadcastStrategy",
    "BatchBroadcastStrategy",
    "AdaptiveBatchStrategy",
    "BroadcastObserver",
    "MetricsObserverAdapter",
    "create_default_router",
    "create_adaptive_router",
    # Tenant filter
    "TenantFilter",
    "TenantAwareBroadcaster",
]
