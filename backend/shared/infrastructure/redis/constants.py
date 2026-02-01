"""
Redis constants and configuration.
Centralizes TTLs and key prefixes for better visibility and management.
"""

# =============================================================================
# TTL (Time To Live) Constants (in seconds)
# =============================================================================

# Authentication
JWT_BLACKLIST_TTL = 3600  # 1 hour (should match generic access token lifetime)
# Note: Specific token blacklisting uses the token's remaining lifetime

# Caching
PRODUCT_CACHE_TTL = 300  # 5 minutes
BRANCH_PRODUCTS_CACHE_TTL = 300  # 5 minutes

# Rate Limiting
# Note: Rate limits use windows defined in settings, not fixed constants here

# Retry & Dead Letter Queues
WEBHOOK_RETRY_PENDING_TTL = 86400 * 7  # 7 days retention for pending retries
WEBHOOK_DEAD_LETTER_TTL = 86400 * 30   # 30 days retention for dead letters


# =============================================================================
# Key Prefixes
# =============================================================================

PREFIX_AUTH_BLACKLIST = "auth:token:blacklist:"
PREFIX_AUTH_USER_REVOKE = "auth:user:revoked:"

PREFIX_CACHE_PRODUCT = "cache:product:"
# PERF-MED-04 FIX: Template for branch products cache key
PREFIX_CACHE_BRANCH_PRODUCTS_TEMPLATE = "cache:branch:{branch_id}:tenant:{tenant_id}:products"


def get_branch_products_cache_key(branch_id: int, tenant_id: int) -> str:
    """PERF-MED-04: Generate cache key for branch products with consistent prefix."""
    return PREFIX_CACHE_BRANCH_PRODUCTS_TEMPLATE.format(branch_id=branch_id, tenant_id=tenant_id)

PREFIX_RATELIMIT_LOGIN = "ratelimit:login:"

PREFIX_WEBHOOK_RETRY = "webhook:retry:"
PREFIX_WEBHOOK_DEAD_LETTER = "webhook:dead_letter:"

# =============================================================================
# Stream Keys & Consumer Groups
# =============================================================================

# Critical events stream (Orders, Payments)
STREAM_EVENTS_CRITICAL = "events:critical"
# Consumer group for WebSocket Gateway
CONSUMER_GROUP_WS_GATEWAY = "ws_gateway_group"

