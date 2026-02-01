"""
WebSocket Gateway Components.

ARCH-REFACTOR-01: Reorganized into domain-specific modules:
- core/       - Foundational components (constants, context, DI)
- connection/ - Connection lifecycle (locks, heartbeat, rate limiting)
- events/     - Event handling (types, router)
- broadcast/  - Message broadcasting (router, tenant filter)
- auth/       - Authentication strategies (JWT, TableToken)
- endpoints/  - WebSocket endpoints (base, mixins, handlers)
- resilience/ - Fault tolerance (circuit breaker, retry)
- metrics/    - Observability (collector, prometheus)
- data/       - Data access (sector repository)

Backward Compatibility:
All public symbols are re-exported here for existing import paths.
New code should import from specific submodules for clarity.
"""

# =============================================================================
# Core Components
# =============================================================================
from ws_gateway.components.core.constants import (
    WSCloseCode,
    WSConstants,
    MSG_PING_PLAIN,
    MSG_PING_JSON,
    MSG_PONG_JSON,
    MSG_REFRESH_SECTORS,
    DEFAULT_ALLOWED_ORIGINS,
    validate_websocket_origin,
)
from ws_gateway.components.core.context import WebSocketContext, sanitize_log_data
from ws_gateway.components.core.dependencies import (
    ConnectionManagerDependencies,
    get_lock_manager,
    get_metrics_collector,
    get_heartbeat_tracker,
    get_rate_limiter,
    reset_singletons,
)

# =============================================================================
# Connection Management
# =============================================================================
from ws_gateway.components.connection.index import ConnectionIndex
from ws_gateway.components.connection.locks import LockManager
from ws_gateway.components.connection.lock_sequence import (
    LockSequence,
    LockOrder,
    DeadlockRiskError,
    with_user_and_branches,
    with_counter_and_user,
)
from ws_gateway.components.connection.heartbeat import HeartbeatTracker, handle_heartbeat
from ws_gateway.components.connection.rate_limiter import WebSocketRateLimiter

# =============================================================================
# Events
# =============================================================================
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

# =============================================================================
# Broadcasting
# =============================================================================
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
from ws_gateway.components.broadcast.tenant_filter import TenantFilter, TenantAwareBroadcaster

# =============================================================================
# Authentication
# =============================================================================
from ws_gateway.components.auth.strategies import (
    AuthStrategy,
    AuthResult,
    JWTAuthStrategy,
    TableTokenAuthStrategy,
    CompositeAuthStrategy,
    NullAuthStrategy,
)

# =============================================================================
# Endpoints
# =============================================================================
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

# =============================================================================
# Resilience
# =============================================================================
from ws_gateway.components.resilience.circuit_breaker import CircuitBreaker, CircuitState
from ws_gateway.components.resilience.retry import (
    RetryConfig,
    calculate_delay_with_jitter,
    DecorrelatedJitter,
)

# =============================================================================
# Metrics
# =============================================================================
from ws_gateway.components.metrics.collector import MetricsCollector
from ws_gateway.components.metrics.prometheus import (
    PrometheusFormatter,
    generate_prometheus_metrics,
)

# =============================================================================
# Data Access
# =============================================================================
from ws_gateway.components.data.sector_repository import (
    SectorAssignmentRepository,
    SectorCache,
    get_sector_repository,
    get_waiter_sector_ids,
    cleanup_sector_repository,
    reset_sector_repository,
)

# =============================================================================
# Redis Utilities (REDIS-01/02 FIX)
# =============================================================================
from ws_gateway.components.redis.lua_scripts import (
    execute_rate_limit_check,
    pipeline_broadcast_acks,
)

# =============================================================================
# Public API
# =============================================================================
__all__ = [
    # Core
    "WSCloseCode",
    "WSConstants",
    "MSG_PING_PLAIN",
    "MSG_PING_JSON",
    "MSG_PONG_JSON",
    "MSG_REFRESH_SECTORS",
    "DEFAULT_ALLOWED_ORIGINS",
    "validate_websocket_origin",
    "WebSocketContext",
    "sanitize_log_data",
    "ConnectionManagerDependencies",
    "get_lock_manager",
    "get_metrics_collector",
    "get_heartbeat_tracker",
    "get_rate_limiter",
    "reset_singletons",
    # Connection
    "ConnectionIndex",
    "LockManager",
    "LockSequence",
    "LockOrder",
    "DeadlockRiskError",
    "with_user_and_branches",
    "with_counter_and_user",
    "HeartbeatTracker",
    "handle_heartbeat",
    "WebSocketRateLimiter",
    # Events
    "WebSocketEvent",
    "EventType",
    "VALID_EVENT_TYPES",
    "REQUIRED_EVENT_FIELDS",
    "OPTIONAL_EVENT_FIELDS",
    "EventRouter",
    "RoutingResult",
    "safe_int",
    # Broadcasting
    "BroadcastRouter",
    "BroadcastStrategy",
    "BatchBroadcastStrategy",
    "AdaptiveBatchStrategy",
    "BroadcastObserver",
    "MetricsObserverAdapter",
    "create_default_router",
    "create_adaptive_router",
    "TenantFilter",
    "TenantAwareBroadcaster",
    # Authentication
    "AuthStrategy",
    "AuthResult",
    "JWTAuthStrategy",
    "TableTokenAuthStrategy",
    "CompositeAuthStrategy",
    "NullAuthStrategy",
    # Endpoints
    "WebSocketEndpointBase",
    "JWTWebSocketEndpoint",
    "MessageValidationMixin",
    "OriginValidationMixin",
    "JWTRevalidationMixin",
    "HeartbeatMixin",
    "ConnectionLifecycleMixin",
    "WaiterEndpoint",
    "KitchenEndpoint",
    "AdminEndpoint",
    "DinerEndpoint",
    # Resilience
    "CircuitBreaker",
    "CircuitState",
    "RetryConfig",
    "calculate_delay_with_jitter",
    "DecorrelatedJitter",
    # Metrics
    "MetricsCollector",
    "PrometheusFormatter",
    "generate_prometheus_metrics",
    # Data
    "SectorAssignmentRepository",
    "SectorCache",
    "get_sector_repository",
    "get_waiter_sector_ids",
    "cleanup_sector_repository",
    "reset_sector_repository",
    # Redis
    "execute_rate_limit_check",
    "pipeline_broadcast_acks",
]
