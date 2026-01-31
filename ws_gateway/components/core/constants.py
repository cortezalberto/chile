"""
WebSocket Gateway Constants.

Centralized constants with documentation explaining rationale for each value.
ARCH-AP-02 FIX: Eliminated magic numbers by documenting all values.
MED-DEEP-04 FIX: Moved all imports to module level per PEP 8.
"""

from enum import IntEnum
from typing import Final, Protocol

# LOW-NEW-04 FIX: Explicit exports for clean imports
__all__ = [
    "WSCloseCode",
    "WSConstants",
    "MSG_PING_PLAIN",
    "MSG_PING_JSON",
    "MSG_PONG_JSON",
    "MSG_REFRESH_SECTORS",
    "DEFAULT_ALLOWED_ORIGINS",
    "validate_websocket_origin",
    "HasStats",
]


class WSCloseCode(IntEnum):
    """
    WebSocket close codes used by the gateway.

    Standard codes (1000-1999) from RFC 6455.
    Custom codes (4000-4999) for application-specific errors.

    LOW-WS-02 FIX: Documented custom codes with project-specific meanings.
    See also: CLAUDE.md "WebSocket Events" section for client handling.
    """

    # Standard codes (RFC 6455)
    NORMAL = 1000  # Normal closure
    GOING_AWAY = 1001  # Server shutting down or client navigating away
    PROTOCOL_ERROR = 1002  # Protocol error
    UNSUPPORTED_DATA = 1003  # Received data type not supported
    POLICY_VIOLATION = 1008  # Generic policy violation
    MESSAGE_TOO_BIG = 1009  # Message too large to process
    SERVER_ERROR = 1011  # Unexpected server error
    SERVER_OVERLOADED = 1013  # Server overloaded, try again later

    # Custom application codes (4000-4999)
    # LOW-WS-02: These codes are documented in CLAUDE.md and used by all frontends
    AUTH_FAILED = 4001  # JWT/table token validation failed or expired
    FORBIDDEN = 4003  # Valid auth but insufficient permissions or invalid origin
    RATE_LIMITED = 4029  # Too many messages per second (see ws_message_rate_limit setting)


class WSConstants:
    """
    WebSocket Gateway operational constants.

    Each constant is documented with the rationale for its value.
    Values can be overridden via settings when marked as configurable.

    LOW-WS-01 NOTE: Default Values vs Settings
    ==========================================
    These are COMPILE-TIME defaults used when settings are not available.
    At RUNTIME, the ConnectionManager and other components read from
    `shared.settings.settings` which can override these values via
    environment variables. The settings take precedence.

    Configurable via settings.py:
    - WS_RECEIVE_TIMEOUT -> settings.ws_receive_timeout (not yet added)
    - JWT_REVALIDATION_INTERVAL -> settings.jwt_revalidation_interval (not yet added)
    - MAX_TRACKED_CONNECTIONS -> derived from settings.ws_max_total_connections

    Not configurable (internal implementation details):
    - Lock management thresholds
    - Circuit breaker parameters
    - Eviction percentages
    """

    # ==========================================================================
    # Timeout Constants
    # ==========================================================================

    # WS_RECEIVE_TIMEOUT: 90 seconds
    # Rationale: Must be longer than heartbeat interval (30s) to avoid false
    # positives. At 3x the heartbeat interval, allows for network jitter and
    # client delays while still detecting truly dead connections.
    WS_RECEIVE_TIMEOUT: Final[float] = 90.0

    # JWT_REVALIDATION_INTERVAL: 5 minutes (300 seconds)
    # Rationale: Balances security vs performance. Shorter intervals catch
    # revoked tokens faster but add Redis overhead. 5 minutes means a revoked
    # token has max 5 min window of use for existing connections.
    JWT_REVALIDATION_INTERVAL: Final[float] = 300.0

    # DB_LOOKUP_TIMEOUT: 2 seconds
    # Rationale: Sector assignment lookups should be fast (<100ms typical).
    # 2 seconds is generous to handle slow DB but prevents blocking the
    # event loop if DB is unresponsive. After timeout, waiter receives
    # all branch events as fallback.
    DB_LOOKUP_TIMEOUT: Final[float] = 2.0

    # WS_ACCEPT_TIMEOUT: 5 seconds
    # Rationale: WebSocket handshake should complete within TCP timeout.
    # 5 seconds handles slow networks while rejecting stuck connections.
    WS_ACCEPT_TIMEOUT: Final[float] = 5.0

    # ==========================================================================
    # Lock Management Constants
    # ==========================================================================

    # MAX_CACHED_LOCKS: 500
    # Rationale: Typical deployment has 10-50 branches. 500 allows for 10x
    # growth while limiting memory usage. Each lock is ~200 bytes, so 500
    # locks use ~100KB - negligible memory footprint.
    MAX_CACHED_LOCKS: Final[int] = 500

    # LOCK_CLEANUP_THRESHOLD: 400 (80% of MAX_CACHED_LOCKS)
    # Rationale: Start cleanup before hitting the limit to avoid blocking.
    # 80% threshold provides buffer for burst of new branches while
    # triggering proactive cleanup.
    LOCK_CLEANUP_THRESHOLD: Final[int] = 400

    # LOCK_CLEANUP_HYSTERESIS_RATIO: 0.8 (80%)
    # Rationale: When cleanup runs, reduce lock count to 80% of threshold.
    # This hysteresis prevents "cleanup thrashing" where we repeatedly
    # hit threshold, clean 1 lock, hit threshold again. With 0.8 ratio:
    # - At 400 locks (threshold), cleanup triggers
    # - Reduces to 320 locks (80% of 400), leaving 80-lock buffer
    # - Next cleanup won't trigger until 400 again
    # This pattern is common in cache eviction (see Redis maxmemory-samples).
    LOCK_CLEANUP_HYSTERESIS_RATIO: Final[float] = 0.8

    # ==========================================================================
    # Rate Limiter Constants
    # ==========================================================================

    # MAX_TRACKED_CONNECTIONS: 2000
    # Rationale: With MAX_TOTAL_CONNECTIONS=1000, this allows 2x headroom
    # for connections being cleaned up or in transition states. Prevents
    # memory leak from tracking already-disconnected connections.
    MAX_TRACKED_CONNECTIONS: Final[int] = 2000

    # EVICTION_PERCENTAGE: 10%
    # Rationale: When rate limiter is at capacity, remove 10% oldest entries.
    # Small enough to avoid performance spike, large enough to create
    # breathing room for new connections.
    EVICTION_PERCENTAGE: Final[int] = 10

    # ==========================================================================
    # Event Queue Constants
    # ==========================================================================

    # DROP_LOG_INTERVAL: 100
    # Rationale: Log every 100th dropped event to avoid log spam during
    # overload while still providing visibility. At 1000 events/sec max,
    # this logs at most 10 times/sec during sustained overload.
    DROP_LOG_INTERVAL: Final[int] = 100

    # MAX_UNKNOWN_FIELDS: 10
    # LOW-WS-04 FIX: Documented rationale more explicitly
    # Rationale: Events typically have 1-5 extra fields for forward compatibility.
    # More than 10 unknown fields strongly indicates:
    # - Malformed event from buggy publisher
    # - Version mismatch between services
    # - Potential injection attack (crafted payload)
    # This threshold balances forward compatibility with security.
    # Adjust to 15 if legitimate events routinely have more fields.
    MAX_UNKNOWN_FIELDS: Final[int] = 10

    # ==========================================================================
    # Sector Validation Constants (MED-01 FIX)
    # ==========================================================================

    # MAX_SECTORS_PER_WAITER: 10
    # Rationale: Typical restaurant has 2-5 sectors per branch. A waiter
    # assigned to more than 10 sectors is suspicious and may indicate
    # misconfiguration or attack. This is a warning threshold, not hard limit.
    MAX_SECTORS_PER_WAITER: Final[int] = 10

    # ==========================================================================
    # Unknown Event Types Tracking
    # ==========================================================================

    # MAX_UNKNOWN_EVENT_TYPES: 100
    # Rationale: Prevents unbounded memory growth if attacker sends random
    # event types. 100 unique types is generous for forward compatibility
    # while limiting memory to ~10KB worst case.
    # DEF-02 FIX: Added limit to _unknown_event_types_seen set.
    MAX_UNKNOWN_EVENT_TYPES: Final[int] = 100

    # ==========================================================================
    # Circuit Breaker Constants
    # ==========================================================================

    # CIRCUIT_FAILURE_THRESHOLD: 5
    # Rationale: 5 consecutive failures before opening circuit. Handles
    # transient errors while quickly detecting sustained failures.
    CIRCUIT_FAILURE_THRESHOLD: Final[int] = 5

    # CIRCUIT_RECOVERY_TIMEOUT: 30 seconds
    # Rationale: Time in OPEN state before attempting recovery. 30 seconds
    # allows dependent services time to recover without leaving circuit
    # open too long.
    CIRCUIT_RECOVERY_TIMEOUT: Final[float] = 30.0

    # CIRCUIT_HALF_OPEN_MAX_CALLS: 3
    # Rationale: Number of test calls allowed in HALF_OPEN state. 3 calls
    # confirm recovery without overwhelming a still-recovering service.
    CIRCUIT_HALF_OPEN_MAX_CALLS: Final[int] = 3

    # ==========================================================================
    # Heartbeat Constants
    # ==========================================================================

    # HEARTBEAT_CLEANUP_INTERVAL: 30 seconds
    # Rationale: Check for stale connections every 30 seconds. Matches
    # typical client ping interval. More frequent checks waste CPU,
    # less frequent delays dead connection cleanup.
    HEARTBEAT_CLEANUP_INTERVAL: Final[float] = 30.0

    # LOCK_CLEANUP_CYCLE: 5 (every 5 heartbeat cycles = 2.5 minutes)
    # Rationale: Lock cleanup is less urgent than connection cleanup.
    # Running every 2.5 minutes balances memory reclamation with CPU usage.
    LOCK_CLEANUP_CYCLE: Final[int] = 5

    # ==========================================================================
    # HIGH-NEW-01 FIX: Broadcast Rate Limiting
    # ==========================================================================

    # MAX_BROADCASTS_PER_SECOND: 10
    # Rationale: Global broadcasts are expensive (send to ALL connections).
    # Limit to 10/sec to prevent DoS via broadcast spam. Normal operation
    # uses targeted sends (to branch/sector/session), not global broadcasts.
    MAX_BROADCASTS_PER_SECOND: Final[int] = 10

    # ==========================================================================
    # HIGH-NEW-02 FIX: Dead Connections Limit
    # ==========================================================================

    # MAX_DEAD_CONNECTIONS: 500
    # Rationale: Limit size of _dead_connections set to prevent unbounded
    # memory growth. When limit is reached, oldest entries are cleaned up
    # immediately instead of waiting for periodic cleanup.
    MAX_DEAD_CONNECTIONS: Final[int] = 500


# Message type constants for heartbeat protocol
MSG_PING_PLAIN: Final[str] = "ping"
MSG_PING_JSON: Final[str] = '{"type":"ping"}'
MSG_PONG_JSON: Final[str] = '{"type":"pong"}'
MSG_REFRESH_SECTORS: Final[str] = "refresh_sectors"


# ==========================================================================
# HIGH-NEW-03 FIX: Shared Origin Validation
# ==========================================================================

# Default development origins (shared between all endpoints)
# HIGH-DEEP-05 FIX: Use tuple instead of list to prevent mutation
DEFAULT_ALLOWED_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5173", "http://localhost:5176",
    "http://localhost:5177", "http://localhost:5178", "http://localhost:5179",
    "http://localhost:5180",  # pwaWaiter fallback port
    "http://127.0.0.1:5173", "http://127.0.0.1:5176",
    "http://127.0.0.1:5177", "http://127.0.0.1:5178", "http://127.0.0.1:5179",
    "http://127.0.0.1:5180",  # pwaWaiter fallback port
    # Local network IP for testing on other devices
    "http://192.168.1.106:5173", "http://192.168.1.106:5176",
    "http://192.168.1.106:5177", "http://192.168.1.106:5178",
    "http://192.168.1.106:5179", "http://192.168.1.106:5180",
)


def validate_websocket_origin(origin: str | None, settings: object) -> bool:
    """
    Validate WebSocket origin header against allowed origins.

    HIGH-NEW-03 FIX: Extracted from JWTWebSocketEndpoint and DinerEndpoint
    to eliminate code duplication.
    HIGH-WS-08 FIX: Stricter validation - logs warning for missing origin,
    doesn't allow bypass via omitting header in production.

    Args:
        origin: The Origin header value, or None if not present.
        settings: Settings object with environment and allowed_origins attributes.

    Returns:
        True if origin is allowed, False otherwise.
    """
    import logging
    _logger = logging.getLogger(__name__)

    # Get allowed origins from settings or use defaults
    allowed_origins_str = getattr(settings, "allowed_origins", None)
    if allowed_origins_str:
        allowed = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]
    else:
        allowed = list(DEFAULT_ALLOWED_ORIGINS)

    # HIGH-WS-08 FIX: Handle missing origin header more strictly
    if not origin:
        is_dev = getattr(settings, "environment", "production") == "development"
        if is_dev:
            # Log warning even in dev mode to help detect potential issues
            _logger.warning(
                "WebSocket connection with missing Origin header (allowed in dev mode only)",
            )
            return True
        else:
            _logger.warning(
                "WebSocket connection rejected: missing Origin header in production",
            )
            return False

    # Validate origin against allowed list
    if origin in allowed:
        return True

    _logger.warning(
        "WebSocket connection rejected: origin not in allowed list",
        extra={"origin": origin, "allowed_count": len(allowed)},
    )
    return False


# ==========================================================================
# LOW-WS-03 FIX: Common Stats Interface
# ==========================================================================
# MED-DEEP-04 FIX: Protocol and runtime_checkable imported at module level


class HasStats(Protocol):
    """
    Protocol for components that provide statistics.

    LOW-WS-03 FIX: Common interface for aggregating stats from
    different components (rate_limiter, metrics_collector, etc.).

    MED-AUD-07 FIX: Removed @runtime_checkable decorator since no
    isinstance() checks are performed against this Protocol.
    This eliminates unnecessary overhead from __subclasshook__.

    All stats methods should return a dict with string keys.
    """

    def get_stats(self) -> dict[str, int | float | str]:
        """Return component statistics as a dictionary."""
        ...
