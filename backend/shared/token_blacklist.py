"""
Token blacklist service using Redis.

Provides token revocation capability for:
- User logout
- Password change
- Account deactivation
- Security incidents

Tokens are stored in Redis with TTL matching their expiration.
"""

# LOW-01 FIX: Removed unused Optional import
import asyncio
from datetime import datetime, timezone

from shared.events import get_redis_pool
from shared.settings import settings
from shared.logging import get_logger

logger = get_logger(__name__)

# Redis key prefix for blacklisted tokens
BLACKLIST_PREFIX = "token_blacklist:"

# Redis key prefix for user revocation (revokes all tokens issued before timestamp)
USER_REVOKE_PREFIX = "user_revoke:"


async def blacklist_token(token_jti: str, expires_at: datetime) -> bool:
    """
    Add a token to the blacklist.

    Args:
        token_jti: JWT token ID (jti claim)
        expires_at: Token expiration time

    Returns:
        True if successfully blacklisted, False otherwise

    Note:
        The token is stored with TTL = (expires_at - now) so it's automatically
        cleaned up after expiration.
    """
    try:
        redis = await get_redis_pool()

        # Calculate TTL (time until token expires)
        now = datetime.now(timezone.utc)
        ttl_seconds = int((expires_at - now).total_seconds())

        # Don't blacklist already-expired tokens
        if ttl_seconds <= 0:
            logger.debug("Token already expired, skipping blacklist", jti=token_jti)
            return True

        # Store in Redis with TTL
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        await redis.setex(key, ttl_seconds, "1")

        logger.info("Token blacklisted", jti=token_jti, ttl_seconds=ttl_seconds)
        return True

    except Exception as e:
        logger.error("Failed to blacklist token", jti=token_jti, error=str(e))
        return False


async def is_token_blacklisted(token_jti: str) -> bool:
    """
    Check if a token is blacklisted.

    Args:
        token_jti: JWT token ID (jti claim)

    Returns:
        True if token is blacklisted, False otherwise
    """
    try:
        redis = await get_redis_pool()
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        result = await redis.exists(key)
        return result > 0

    except Exception as e:
        # Log error but don't block auth - fail open for availability
        logger.error("Failed to check token blacklist", jti=token_jti, error=str(e))
        return False


async def revoke_all_user_tokens(user_id: int) -> bool:
    """
    Revoke all tokens for a user by storing a revocation timestamp.

    Any token issued before this timestamp is considered revoked.
    This is useful for:
    - Password change (invalidate all sessions)
    - Account compromise
    - User deactivation

    Args:
        user_id: User ID to revoke tokens for

    Returns:
        True if successfully revoked, False otherwise
    """
    try:
        redis = await get_redis_pool()

        # Store revocation timestamp
        # TTL = refresh token lifetime (longest-lived token)
        key = f"{USER_REVOKE_PREFIX}{user_id}"
        now = datetime.now(timezone.utc)
        ttl_seconds = settings.jwt_refresh_token_expire_days * 24 * 60 * 60

        await redis.setex(key, ttl_seconds, now.isoformat())

        logger.info("All tokens revoked for user", user_id=user_id)
        return True

    except Exception as e:
        logger.error("Failed to revoke user tokens", user_id=user_id, error=str(e))
        return False


async def is_token_revoked_by_user(user_id: int, token_iat: datetime) -> bool:
    """
    Check if a token was revoked by user-level revocation.

    Args:
        user_id: User ID from token
        token_iat: Token issued-at time (iat claim)

    Returns:
        True if token was issued before user revocation, False otherwise
    """
    try:
        redis = await get_redis_pool()
        key = f"{USER_REVOKE_PREFIX}{user_id}"
        revoke_time_str = await redis.get(key)

        if not revoke_time_str:
            return False

        # CRIT-29-06 FIX: decode_responses=True in get_redis_pool() already returns string
        # No need to decode - revoke_time_str is already a string
        revoke_time = datetime.fromisoformat(revoke_time_str)

        # Token is revoked if it was issued before the revocation
        return token_iat < revoke_time

    except Exception as e:
        # Log error but don't block auth - fail open
        logger.error("Failed to check user token revocation", user_id=user_id, error=str(e))
        return False


async def check_token_validity(token_jti: str, user_id: int, token_iat: datetime) -> bool:
    """
    Combined check for token validity.

    Checks both:
    1. Individual token blacklist
    2. User-level revocation

    Args:
        token_jti: JWT token ID
        user_id: User ID from token
        token_iat: Token issued-at time

    Returns:
        True if token is valid, False if revoked
    """
    # Check individual blacklist
    if await is_token_blacklisted(token_jti):
        return False

    # Check user-level revocation
    if await is_token_revoked_by_user(user_id, token_iat):
        return False

    return True


# =============================================================================
# SHARED-CRIT-01 FIX: Synchronous wrappers using Redis sync client
# Avoid mixing async/sync contexts which causes deadlocks with ThreadPoolExecutor
# =============================================================================

# Redis sync client singleton for sync operations
_redis_sync_client = None
_sync_client_lock = None  # Will be initialized on first use

def _get_redis_sync_client():
    """
    Get a synchronous Redis client for sync contexts.
    SHARED-CRIT-01 FIX: Uses a separate sync client to avoid async/sync mixing.
    """
    global _redis_sync_client
    if _redis_sync_client is None:
        import redis as redis_sync
        from shared.settings import REDIS_URL
        _redis_sync_client = redis_sync.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_sync_client


def blacklist_token_sync(token_jti: str, expires_at: datetime) -> bool:
    """
    Synchronous wrapper for blacklist_token.
    SHARED-CRIT-01 FIX: Uses sync Redis client to avoid async/sync context mixing.
    """
    try:
        redis_client = _get_redis_sync_client()

        # Calculate TTL (time until token expires)
        now = datetime.now(timezone.utc)
        ttl_seconds = int((expires_at - now).total_seconds())

        # Don't blacklist already-expired tokens
        if ttl_seconds <= 0:
            logger.debug("Token already expired, skipping blacklist", jti=token_jti)
            return True

        # Store in Redis with TTL
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        redis_client.setex(key, ttl_seconds, "1")

        logger.info("Token blacklisted (sync)", jti=token_jti, ttl_seconds=ttl_seconds)
        return True

    except Exception as e:
        logger.error("Failed to blacklist token (sync)", jti=token_jti, error=str(e))
        return False


def is_token_blacklisted_sync(token_jti: str) -> bool:
    """
    Synchronous wrapper for is_token_blacklisted.
    SHARED-CRIT-01 FIX: Uses sync Redis client to avoid async/sync context mixing.
    """
    try:
        redis_client = _get_redis_sync_client()
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        result = redis_client.exists(key)
        return result > 0

    except Exception as e:
        # Log error but don't block auth - fail open for availability
        logger.error("Failed to check token blacklist (sync)", jti=token_jti, error=str(e))
        return False


def is_token_revoked_by_user_sync(user_id: int, token_iat: datetime) -> bool:
    """
    Synchronous wrapper for is_token_revoked_by_user.
    SHARED-CRIT-01 FIX: Uses sync Redis client to avoid async/sync context mixing.
    """
    try:
        redis_client = _get_redis_sync_client()
        key = f"{USER_REVOKE_PREFIX}{user_id}"
        revoke_time_str = redis_client.get(key)

        if not revoke_time_str:
            return False

        revoke_time = datetime.fromisoformat(revoke_time_str)

        # Token is revoked if it was issued before the revocation
        return token_iat < revoke_time

    except Exception as e:
        # Log error but don't block auth - fail open
        logger.error("Failed to check user token revocation (sync)", user_id=user_id, error=str(e))
        return False
