"""
Token blacklist service using Redis.

Provides token revocation capability for:
- User logout
- Password change
- Account deactivation
- Security incidents

Tokens are stored in Redis with TTL matching their expiration.

REDIS-AUDIT FIX: Refactored to use shared Redis clients from events.py.
- REDIS-CRIT-02/03: Now uses coordinated clients from events.py
- REDIS-HIGH-01: Standardized key prefixes
- REDIS-HIGH-02: Uses unified timeout settings
- REDIS-MED-02: Consistent logging (added sync=True/False field)
"""

from datetime import datetime, timezone

from shared.infrastructure.events import get_redis_pool, get_redis_sync_client
from shared.config.settings import settings
from shared.config.logging import get_logger

logger = get_logger(__name__)

from shared.infrastructure.redis.constants import PREFIX_AUTH_BLACKLIST, PREFIX_AUTH_USER_REVOKE
# REDIS-HIGH-01 FIX: Standardized key prefixes with service namespace
BLACKLIST_PREFIX = PREFIX_AUTH_BLACKLIST
USER_REVOKE_PREFIX = PREFIX_AUTH_USER_REVOKE



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
            logger.debug("Token already expired, skipping blacklist", jti=token_jti, sync=False)
            return True

        # Store in Redis with TTL
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        await redis.setex(key, ttl_seconds, "1")

        logger.info("Token blacklisted", jti=token_jti, ttl_seconds=ttl_seconds, sync=False)
        return True

    except Exception as e:
        logger.error("Failed to blacklist token", jti=token_jti, error=str(e), sync=False)
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
        # CRIT-02 FIX: Fail CLOSED on Redis errors for security
        # If we can't verify the token isn't blacklisted, deny access
        logger.error(
            "Failed to check token blacklist - failing closed",
            jti=token_jti,
            error=str(e),
            sync=False,
        )
        return True  # Treat as blacklisted (fail closed)


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

        logger.info("All tokens revoked for user", user_id=user_id, sync=False)
        return True

    except Exception as e:
        logger.error("Failed to revoke user tokens", user_id=user_id, error=str(e), sync=False)
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

        # decode_responses=True in get_redis_pool() already returns string
        revoke_time = datetime.fromisoformat(revoke_time_str)

        # Token is revoked if it was issued before the revocation
        return token_iat < revoke_time

    except Exception as e:
        # CRIT-02 FIX: Fail CLOSED on Redis errors for security
        # If we can't verify the token isn't revoked, deny access
        logger.error(
            "Failed to check user token revocation - failing closed",
            user_id=user_id,
            error=str(e),
            sync=False,
        )
        return True  # Treat as revoked (fail closed)


async def check_token_validity(token_jti: str, user_id: int, token_iat: datetime) -> bool:
    """
    Combined check for token validity.

    PERF-CRIT-01 FIX: Uses Redis PIPELINE to reduce 2 round-trips to 1.

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
    try:
        redis = await get_redis_pool()
        blacklist_key = f"{BLACKLIST_PREFIX}{token_jti}"
        revoke_key = f"{USER_REVOKE_PREFIX}{user_id}"

        # PERF-CRIT-01 FIX: Single round-trip with pipeline
        async with redis.pipeline(transaction=False) as pipe:
            pipe.exists(blacklist_key)
            pipe.get(revoke_key)
            results = await pipe.execute()

        # Check blacklist result
        is_blacklisted = results[0] > 0
        if is_blacklisted:
            return False

        # Check user-level revocation
        revoke_time_str = results[1]
        if revoke_time_str:
            revoke_time = datetime.fromisoformat(revoke_time_str)
            if token_iat < revoke_time:
                return False

        return True

    except Exception as e:
        # CRIT-02 FIX: Fail CLOSED on Redis errors for security
        logger.error(
            "Failed to check token validity - failing closed",
            jti=token_jti,
            user_id=user_id,
            error=str(e),
            sync=False,
        )
        return False  # Treat as invalid (fail closed)


# =============================================================================
# Synchronous wrappers using shared Redis sync client
# REDIS-CRIT-02/03 FIX: Uses coordinated client from events.py
# =============================================================================


def blacklist_token_sync(token_jti: str, expires_at: datetime) -> bool:
    """
    Synchronous wrapper for blacklist_token.
    Uses shared sync Redis client from events.py.
    """
    try:
        redis_client = get_redis_sync_client()

        # Calculate TTL (time until token expires)
        now = datetime.now(timezone.utc)
        ttl_seconds = int((expires_at - now).total_seconds())

        # Don't blacklist already-expired tokens
        if ttl_seconds <= 0:
            logger.debug("Token already expired, skipping blacklist", jti=token_jti, sync=True)
            return True

        # Store in Redis with TTL
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        redis_client.setex(key, ttl_seconds, "1")

        logger.info("Token blacklisted", jti=token_jti, ttl_seconds=ttl_seconds, sync=True)
        return True

    except Exception as e:
        logger.error("Failed to blacklist token", jti=token_jti, error=str(e), sync=True)
        return False


def is_token_blacklisted_sync(token_jti: str) -> bool:
    """
    Synchronous wrapper for is_token_blacklisted.
    Uses shared sync Redis client from events.py.
    """
    try:
        redis_client = get_redis_sync_client()
        key = f"{BLACKLIST_PREFIX}{token_jti}"
        result = redis_client.exists(key)
        return result > 0

    except Exception as e:
        # CRIT-02 FIX: Fail CLOSED on Redis errors for security
        logger.error(
            "Failed to check token blacklist - failing closed",
            jti=token_jti,
            error=str(e),
            sync=True,
        )
        return True  # Treat as blacklisted (fail closed)


def is_token_revoked_by_user_sync(user_id: int, token_iat: datetime) -> bool:
    """
    Synchronous wrapper for is_token_revoked_by_user.
    Uses shared sync Redis client from events.py.
    """
    try:
        redis_client = get_redis_sync_client()
        key = f"{USER_REVOKE_PREFIX}{user_id}"
        revoke_time_str = redis_client.get(key)

        if not revoke_time_str:
            return False

        revoke_time = datetime.fromisoformat(revoke_time_str)

        # Token is revoked if it was issued before the revocation
        return token_iat < revoke_time

    except Exception as e:
        # CRIT-02 FIX: Fail CLOSED on Redis errors for security
        logger.error(
            "Failed to check user token revocation - failing closed",
            user_id=user_id,
            error=str(e),
            sync=True,
        )
        return True  # Treat as revoked (fail closed)


def check_token_validity_sync(token_jti: str, user_id: int, token_iat: datetime) -> bool:
    """
    Synchronous combined check for token validity.
    Uses shared sync Redis client from events.py.

    Checks both:
    1. Individual token blacklist
    2. User-level revocation

    Returns:
        True if token is valid, False if revoked
    """
    # Check individual blacklist
    if is_token_blacklisted_sync(token_jti):
        return False

    # Check user-level revocation
    if is_token_revoked_by_user_sync(user_id, token_iat):
        return False

    return True
