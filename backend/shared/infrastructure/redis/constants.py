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
PREFIX_CACHE_BRANCH_PRODUCTS = "branch:{branch_id}:tenant:{tenant_id}:products_complete"

PREFIX_RATELIMIT_LOGIN = "ratelimit:login:"

PREFIX_WEBHOOK_RETRY = "webhook:retry:"
PREFIX_WEBHOOK_DEAD_LETTER = "webhook:dead_letter:"
