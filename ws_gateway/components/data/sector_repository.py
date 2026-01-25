"""
Repository for Waiter Sector Assignments.

Abstracts database access for sector assignment lookups.
Separates data access from WebSocket handling logic.

ARCH-03 FIX: Implemented Repository pattern for clean architecture.
ARCH-OPP-06 FIX: Added caching layer to reduce database load.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TYPE_CHECKING

from sqlalchemy import select

from ws_gateway.components.core.constants import WSConstants

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Cache Implementation
# =============================================================================


@dataclass
class CacheEntry:
    """Single cache entry with value and expiration time."""

    value: list[int]
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() > self.expires_at


class SectorCache:
    """
    Time-based cache for sector assignments.

    ARCH-OPP-06 FIX: Reduces database load for frequently accessed data.

    Features:
    - TTL-based expiration
    - Thread-safe operations
    - Automatic cleanup of expired entries
    - Size limit to prevent memory growth

    Usage:
        cache = SectorCache(ttl_seconds=60.0)
        cache.set((user_id, tenant_id), sector_ids)
        result = cache.get((user_id, tenant_id))
    """

    def __init__(
        self,
        ttl_seconds: float = 60.0,
        max_size: int = 1000,
        cleanup_threshold: float = 0.8,
    ) -> None:
        """
        Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries.
            max_size: Maximum number of entries before cleanup.
            cleanup_threshold: Trigger cleanup at this % of max_size.
        """
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._cleanup_threshold = cleanup_threshold
        self._entries: dict[tuple[int, int], CacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        """Current number of entries in cache."""
        with self._lock:
            return len(self._entries)

    @property
    def hit_ratio(self) -> float:
        """Cache hit ratio (0.0 to 1.0)."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def get(self, key: tuple[int, int]) -> list[int] | None:
        """
        Get cached value for key.

        Args:
            key: (user_id, tenant_id) tuple.

        Returns:
            Cached sector IDs or None if not found/expired.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._entries[key]
                self._misses += 1
                return None

            self._hits += 1
            return entry.value

    def set(self, key: tuple[int, int], value: list[int]) -> None:
        """
        Store value in cache.

        Args:
            key: (user_id, tenant_id) tuple.
            value: Sector IDs to cache.
        """
        with self._lock:
            # Check if cleanup needed
            if len(self._entries) >= self._max_size * self._cleanup_threshold:
                self._cleanup_expired()

            # If still at capacity after cleanup, evict oldest
            if len(self._entries) >= self._max_size:
                self._evict_oldest()

            expires_at = time.time() + self._ttl
            self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

    def invalidate(self, key: tuple[int, int]) -> None:
        """
        Remove entry from cache.

        Args:
            key: (user_id, tenant_id) tuple.
        """
        with self._lock:
            self._entries.pop(key, None)

    def invalidate_user(self, user_id: int) -> int:
        """
        Remove all entries for a user.

        Args:
            user_id: User ID to invalidate.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            keys_to_remove = [k for k in self._entries if k[0] == user_id]
            for key in keys_to_remove:
                del self._entries[key]
            return len(keys_to_remove)

    def clear(self) -> int:
        """
        Clear all entries.

        Returns:
            Number of entries cleared.
        """
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def _cleanup_expired(self) -> int:
        """
        Remove expired entries (must hold lock).

        Returns:
            Number of entries removed.
        """
        now = time.time()
        keys_to_remove = [
            k for k, v in self._entries.items()
            if v.expires_at < now
        ]
        for key in keys_to_remove:
            del self._entries[key]
        return len(keys_to_remove)

    def _evict_oldest(self) -> None:
        """Evict oldest entry (must hold lock)."""
        if not self._entries:
            return

        oldest_key = min(
            self._entries.keys(),
            key=lambda k: self._entries[k].created_at,
        )
        del self._entries[oldest_key]

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "size": len(self._entries),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": round(self.hit_ratio, 3),
            }

    def reset_stats(self) -> dict[str, Any]:
        """Reset statistics and return previous values."""
        with self._lock:
            stats = {
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": round(self.hit_ratio, 3),
            }
            self._hits = 0
            self._misses = 0
            return stats


class SectorAssignmentRepository:
    """
    Repository for accessing waiter sector assignments.

    Provides async-safe access to sector assignments with timeout
    to prevent blocking the event loop.

    ARCH-OPP-06 FIX: Added caching layer to reduce database load.

    Usage:
        repo = SectorAssignmentRepository()
        sector_ids = await repo.get_waiter_sectors(user_id, tenant_id)

        # With cache control:
        sector_ids = await repo.get_waiter_sectors(user_id, tenant_id, skip_cache=True)
    """

    def __init__(
        self,
        timeout: float = WSConstants.DB_LOOKUP_TIMEOUT,
        cache_ttl: float = 60.0,
        cache_max_size: int = 1000,
    ):
        """
        Initialize the repository.

        Args:
            timeout: Timeout in seconds for database lookups.
            cache_ttl: Cache entry time-to-live in seconds.
            cache_max_size: Maximum cache entries.
        """
        self._timeout = timeout
        # ARCH-OPP-06 FIX: Add caching layer
        self._cache = SectorCache(
            ttl_seconds=cache_ttl,
            max_size=cache_max_size,
        )
        # MED-07 FIX: Add metrics for sector lookup fallback tracking
        self._lookup_success = 0
        self._lookup_timeouts = 0
        self._lookup_errors = 0
        self._fallback_to_empty = 0  # Times fallback to empty sectors occurred

    @property
    def cache(self) -> SectorCache:
        """Access the cache for statistics or manual invalidation."""
        return self._cache

    async def get_waiter_sectors(
        self,
        user_id: int,
        tenant_id: int,
        skip_cache: bool = False,
    ) -> list[int]:
        """
        Get sector IDs assigned to a waiter for today.

        Async-safe with timeout to prevent blocking.

        ARCH-OPP-06 FIX: Uses cache to reduce database load.

        Args:
            user_id: The waiter's user ID.
            tenant_id: The tenant ID.
            skip_cache: If True, bypass cache and query database.

        Returns:
            List of sector IDs the waiter is assigned to.
            Empty list if no assignments or timeout.
        """
        cache_key = (user_id, tenant_id)

        # Check cache first (unless skipped)
        if not skip_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(
                    "Cache hit for waiter sectors",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    sectors=cached,
                )
                return cached

        # Query database
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._get_sectors_sync, user_id, tenant_id),
                timeout=self._timeout,
            )
            # Store in cache
            self._cache.set(cache_key, result)
            # MED-07 FIX: Track successful lookup
            self._lookup_success += 1
            return result
        except asyncio.TimeoutError:
            # MED-07 FIX: Track timeout and fallback
            self._lookup_timeouts += 1
            self._fallback_to_empty += 1
            logger.error(
                "DB lookup timeout for waiter sectors - falling back to empty",
                user_id=user_id,
                tenant_id=tenant_id,
                timeout=self._timeout,
                total_timeouts=self._lookup_timeouts,
            )
            return []
        except Exception as e:
            # MED-07 FIX: Track error and fallback
            self._lookup_errors += 1
            self._fallback_to_empty += 1
            logger.error(
                "Error fetching waiter sectors - falling back to empty",
                user_id=user_id,
                tenant_id=tenant_id,
                error=str(e),
                total_errors=self._lookup_errors,
            )
            return []

    def invalidate_cache(self, user_id: int, tenant_id: int) -> None:
        """
        Invalidate cache entry for a specific user/tenant.

        Call this when sector assignments are updated.

        Args:
            user_id: User ID to invalidate.
            tenant_id: Tenant ID to invalidate.
        """
        self._cache.invalidate((user_id, tenant_id))
        logger.debug(
            "Cache invalidated for waiter sectors",
            user_id=user_id,
            tenant_id=tenant_id,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get repository statistics including cache stats.

        MED-07 FIX: Includes lookup metrics for monitoring fallback rate.
        """
        total_lookups = self._lookup_success + self._lookup_timeouts + self._lookup_errors
        return {
            "timeout": self._timeout,
            "cache": self._cache.get_stats(),
            # MED-07 FIX: Sector lookup metrics
            "lookups": {
                "success": self._lookup_success,
                "timeouts": self._lookup_timeouts,
                "errors": self._lookup_errors,
                "total": total_lookups,
                "fallback_to_empty": self._fallback_to_empty,
                "fallback_rate_percent": round(
                    (self._fallback_to_empty / total_lookups * 100) if total_lookups > 0 else 0.0, 2
                ),
            },
        }

    def _get_sectors_sync(self, user_id: int, tenant_id: int) -> list[int]:
        """
        Synchronous sector lookup.

        Args:
            user_id: The waiter's user ID.
            tenant_id: The tenant ID.

        Returns:
            List of unique sector IDs.
        """
        # LOW-DEEP-01 FIX: Imports are here to avoid circular imports at module level.
        # Python caches imports at interpreter level (sys.modules), so these imports
        # are resolved only once per process, not per function call.
        from shared.infrastructure.db import get_db_context
        from rest_api.models import WaiterSectorAssignment

        try:
            with get_db_context() as db:
                today = date.today()
                # HIGH-DEEP-04 FIX: Use .is_(True) instead of == True for SQLAlchemy
                assignments = db.execute(
                    select(WaiterSectorAssignment.sector_id)
                    .where(
                        WaiterSectorAssignment.waiter_id == user_id,
                        WaiterSectorAssignment.tenant_id == tenant_id,
                        WaiterSectorAssignment.assignment_date == today,
                        WaiterSectorAssignment.is_active.is_(True),
                    )
                ).scalars().all()
                return list(set(assignments))  # Unique sector IDs
        except Exception as e:
            # HIGH-WS-01 FIX: Handle DB pool exhaustion gracefully
            logger.error(
                "Database error in sector lookup",
                user_id=user_id,
                tenant_id=tenant_id,
                error=str(e),
            )
            return []

    def get_sectors_sync(self, user_id: int, tenant_id: int) -> list[int]:
        """
        Synchronous version for non-async contexts.

        Note: Prefer get_waiter_sectors() in async context.

        Args:
            user_id: The waiter's user ID.
            tenant_id: The tenant ID.

        Returns:
            List of sector IDs.
        """
        return self._get_sectors_sync(user_id, tenant_id)

    def clear_cache(self) -> int:
        """
        Clear the sector cache.

        MED-04 FIX: Cleanup hook for graceful shutdown.
        Call this during application shutdown to release memory.

        Returns:
            Number of entries cleared.
        """
        count = self._cache.clear()
        logger.info("Sector cache cleared", entries_cleared=count)
        return count

    def reset_metrics(self) -> dict[str, int]:
        """
        Reset lookup metrics and return previous values.

        Useful for periodic metric collection.

        Returns:
            Previous metric values.
        """
        previous = {
            "lookup_success": self._lookup_success,
            "lookup_timeouts": self._lookup_timeouts,
            "lookup_errors": self._lookup_errors,
            "fallback_to_empty": self._fallback_to_empty,
        }
        self._lookup_success = 0
        self._lookup_timeouts = 0
        self._lookup_errors = 0
        self._fallback_to_empty = 0
        return previous


# Singleton instance for convenience
# CRIT-WS-02 FIX: Thread-safe singleton with double-check locking
_repository: SectorAssignmentRepository | None = None
_repository_lock = threading.Lock()


def get_sector_repository() -> SectorAssignmentRepository:
    """
    Get the singleton SectorAssignmentRepository instance.

    CRIT-WS-02 FIX: Thread-safe with double-check locking pattern.

    Returns:
        SectorAssignmentRepository instance.
    """
    global _repository
    if _repository is None:
        with _repository_lock:
            # Double-check inside lock
            if _repository is None:
                _repository = SectorAssignmentRepository()
    return _repository


async def get_waiter_sector_ids(user_id: int, tenant_id: int) -> list[int]:
    """
    Convenience function to get waiter sector IDs.

    Args:
        user_id: The waiter's user ID.
        tenant_id: The tenant ID.

    Returns:
        List of sector IDs.
    """
    return await get_sector_repository().get_waiter_sectors(user_id, tenant_id)


def cleanup_sector_repository() -> int:
    """
    Cleanup the sector repository singleton on shutdown.

    MED-04 FIX: Provides cleanup hook for graceful shutdown.
    Clears the cache and logs statistics.

    Call this during application shutdown (e.g., in lifespan handler).

    Returns:
        Number of cache entries cleared, or 0 if no repository exists.
    """
    global _repository
    if _repository is not None:
        stats = _repository.get_stats()
        logger.info(
            "Cleaning up sector repository",
            cache_stats=stats.get("cache", {}),
            lookup_stats=stats.get("lookups", {}),
        )
        count = _repository.clear_cache()
        return count
    return 0


def reset_sector_repository() -> None:
    """
    Reset the sector repository singleton.

    MED-04 FIX: For testing purposes and complete shutdown cleanup.
    After calling this, get_sector_repository() will create a new instance.
    """
    global _repository
    with _repository_lock:
        if _repository is not None:
            _repository.clear_cache()
            _repository = None
            logger.debug("Sector repository singleton reset")
