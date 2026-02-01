"""
Lock Manager for WebSocket Gateway.

Manages sharded asyncio locks for branch and user operations.
Prevents contention by using fine-grained locks instead of a global lock.

ARCH-01 FIX: Extracted from ConnectionManager (Single Responsibility).

CRIT-04 LOCK ORDERING CONSTRAINTS:
==================================
The _meta_lock is NON-REENTRANT. Methods that acquire _meta_lock MUST NOT call
other methods that also acquire _meta_lock. Violating this causes deadlock.

Safe call hierarchy (outer -> inner is OK):
- get_branch_lock() -> _schedule_cleanup() (schedules task, doesn't call locked methods)
- get_user_lock() -> _schedule_cleanup()
- cleanup_stale_locks() acquires _meta_lock then calls _cleanup_* (internal only)

PROHIBITED patterns (will deadlock):
- _deferred_cleanup() -> get_branch_lock()  # Would try to re-acquire _meta_lock
- Any cleanup method calling get_*_lock() methods

Internal methods prefixed with _ that are called under _meta_lock:
- _cleanup_unheld_locks(): Safe, operates on dict directly
- _deferred_cleanup(): Safe, acquires _meta_lock itself
- _deferred_cleanup_wrapper(): Safe, just wraps _deferred_cleanup

If adding new functionality that needs locks, either:
1. Don't acquire _meta_lock (use branch/user lock directly)
2. Schedule it as a separate task outside the lock
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ws_gateway.components.core.constants import WSConstants

if TYPE_CHECKING:
    from collections.abc import Set

logger = logging.getLogger(__name__)


class LockManager:
    """
    Manages asyncio locks for branch and user operations.

    Uses sharded locks to reduce contention:
    - Branch locks: One lock per branch for branch-specific operations
    - User locks: One lock per user for user-specific operations

    Includes cleanup mechanism to prevent unbounded memory growth.

    CRIT-WS-12 FIX: Uses controlled dict instead of defaultdict with cleanup.
    """

    def __init__(
        self,
        max_cached_locks: int = WSConstants.MAX_CACHED_LOCKS,
        cleanup_threshold: int = WSConstants.LOCK_CLEANUP_THRESHOLD,
    ):
        """
        Initialize the lock manager.

        Args:
            max_cached_locks: Maximum number of locks to cache before cleanup.
            cleanup_threshold: Number of locks that triggers cleanup.
        """
        self._max_cached_locks = max_cached_locks
        self._cleanup_threshold = cleanup_threshold

        # Lock storage
        self._branch_locks: dict[int, asyncio.Lock] = {}
        self._user_locks: dict[int, asyncio.Lock] = {}

        # Meta-lock for managing lock dictionaries themselves
        self._meta_lock = asyncio.Lock()

        # Dedicated locks for specific operations
        self._sector_lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()
        self._dead_connections_lock = asyncio.Lock()
        self._connection_counter_lock = asyncio.Lock()

        # Metrics
        self._locks_cleaned = 0

        # HIGH-AUD-01 FIX: Track pending cleanup task to prevent memory leak
        # and avoid multiple concurrent cleanup tasks
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_pending = False

    @property
    def sector_lock(self) -> asyncio.Lock:
        """Lock for sector operations."""
        return self._sector_lock

    @property
    def session_lock(self) -> asyncio.Lock:
        """Lock for session operations."""
        return self._session_lock

    @property
    def dead_connections_lock(self) -> asyncio.Lock:
        """Lock for dead connections set."""
        return self._dead_connections_lock

    @property
    def connection_counter_lock(self) -> asyncio.Lock:
        """Lock for atomic connection counter operations."""
        return self._connection_counter_lock

    @property
    def branch_lock_count(self) -> int:
        """Number of branch locks currently cached."""
        return len(self._branch_locks)

    @property
    def user_lock_count(self) -> int:
        """Number of user locks currently cached."""
        return len(self._user_locks)

    @property
    def locks_cleaned_total(self) -> int:
        """Total number of locks cleaned since startup."""
        return self._locks_cleaned

    async def get_tenant_branch_lock(
        self,
        tenant_id: int | None,
        branch_id: int,
    ) -> asyncio.Lock:
        """
        SCALE-MED-01 FIX: Get or create a lock for a specific tenant's branch.
        
        Uses composite key (tenant_id, branch_id) to prevent lock collisions
        between branches with the same ID on different tenants. This is
        important for multi-tenant deployments with many simultaneous branches.
        
        Falls back to branch_id-only key if tenant_id is None (legacy support).
        
        Args:
            tenant_id: The tenant ID (or None for legacy single-tenant).
            branch_id: The branch ID to get a lock for.
            
        Returns:
            asyncio.Lock for the specified tenant branch.
        """
        # Use composite key for tenant isolation, or plain branch_id for legacy
        if tenant_id is not None:
            # Use simple hash for performance, avoiding string allocation
            # Magic number chosen to minimize collisions while keeping ints manageable
            lock_key = tenant_id * 1_000_000 + branch_id
        else:
            lock_key = branch_id
        
        return await self.get_branch_lock(lock_key)

    async def get_branch_lock(self, branch_id: int) -> asyncio.Lock:
        """
        Get or create a lock for a specific branch.

        HIGH-AUD-04 FIX: Always acquires meta_lock for thread-safe access.
        The previous "fast path" that read the dict without lock could cause
        issues during cleanup operations (RuntimeError: dictionary changed).

        HIGH-02 FIX: Cleanup is scheduled but not executed under meta_lock.

        Args:
            branch_id: The branch ID to get a lock for.

        Returns:
            asyncio.Lock for the specified branch.
        """
        needs_cleanup = False

        # HIGH-AUD-04 FIX: Always use meta_lock for safe dict access
        async with self._meta_lock:
            # Check if lock exists
            if branch_id in self._branch_locks:
                return self._branch_locks[branch_id]

            # Create new lock
            # HIGH-02 FIX: Flag cleanup needed but don't block
            if len(self._branch_locks) >= self._cleanup_threshold:
                needs_cleanup = True
            self._branch_locks[branch_id] = asyncio.Lock()
            result = self._branch_locks[branch_id]

        # HIGH-02 FIX: Schedule cleanup outside the lock
        # HIGH-AUD-01 FIX: Coordinate cleanup tasks to prevent memory leak
        if needs_cleanup:
            self._schedule_cleanup()

        return result

    async def get_user_lock(self, user_id: int) -> asyncio.Lock:
        """
        Get or create a lock for a specific user.

        HIGH-AUD-04 FIX: Always acquires meta_lock for thread-safe access.
        HIGH-02 FIX: Cleanup is scheduled but not executed under meta_lock.
        HIGH-AUD-01 FIX: Cleanup tasks are coordinated to prevent memory leak.

        Args:
            user_id: The user ID to get a lock for.

        Returns:
            asyncio.Lock for the specified user.
        """
        needs_cleanup = False

        # HIGH-AUD-04 FIX: Always use meta_lock for safe dict access
        async with self._meta_lock:
            # Check if lock exists
            if user_id in self._user_locks:
                return self._user_locks[user_id]

            # Create new lock
            # HIGH-02 FIX: Flag cleanup needed but don't block
            if len(self._user_locks) >= self._cleanup_threshold:
                needs_cleanup = True
            self._user_locks[user_id] = asyncio.Lock()
            result = self._user_locks[user_id]

        # HIGH-02 FIX: Schedule cleanup outside the lock
        # HIGH-AUD-01 FIX: Coordinate cleanup tasks to prevent memory leak
        if needs_cleanup:
            self._schedule_cleanup()

        return result

    def _schedule_cleanup(self) -> None:
        """
        Schedule a deferred cleanup task if one isn't already pending.

        HIGH-AUD-01 FIX: Prevents memory leak from untracked tasks and
        avoids multiple concurrent cleanup tasks.
        """
        # Skip if cleanup already scheduled
        if self._cleanup_pending:
            return

        # Check if previous task is done and can be replaced
        if self._cleanup_task is not None:
            if not self._cleanup_task.done():
                # Task still running, don't schedule another
                return
            # Clear reference to completed task
            self._cleanup_task = None

        self._cleanup_pending = True
        self._cleanup_task = asyncio.create_task(
            self._deferred_cleanup_wrapper(),
            name="deferred_lock_cleanup"
        )

    async def _deferred_cleanup_wrapper(self) -> None:
        """
        Wrapper for _deferred_cleanup that manages the pending flag.

        HIGH-AUD-01 FIX: Ensures _cleanup_pending is always cleared.
        MED-06 FIX: Clears _cleanup_task reference to prevent memory leak.
        """
        try:
            await self._deferred_cleanup()
        finally:
            self._cleanup_pending = False
            # MED-06 FIX: Clear reference to completed task to allow GC
            self._cleanup_task = None

    async def await_pending_cleanup(self) -> None:
        """
        Wait for any pending cleanup task to complete.

        HIGH-05 FIX: Call this during shutdown to ensure cleanup completes.
        Prevents interrupted cleanup operations.
        """
        if self._cleanup_task is not None and not self._cleanup_task.done():
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Cleanup task timed out during shutdown")
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            except Exception as e:
                logger.warning("Error awaiting cleanup task", error=str(e))

    async def _deferred_cleanup(self) -> None:
        """
        HIGH-02 FIX: Run cleanup in background without blocking lock creation.

        CRIT-NEW-01 FIX: Uses conservative cleanup that only removes unheld locks
        when exceeding threshold, instead of passing empty sets which would
        incorrectly mark ALL locks as stale.

        Acquires meta_lock only for the actual cleanup operation.
        """
        try:
            async with self._meta_lock:
                branch_cleaned = self._cleanup_unheld_locks(self._branch_locks)
                user_cleaned = self._cleanup_unheld_locks(self._user_locks)
                if branch_cleaned + user_cleaned > 0:
                    self._locks_cleaned += branch_cleaned + user_cleaned
                    logger.debug(
                        "Deferred lock cleanup completed",
                        branch_cleaned=branch_cleaned,
                        user_cleaned=user_cleaned,
                    )
        except Exception as e:
            logger.warning("Deferred lock cleanup failed", error=str(e))

    def _cleanup_unheld_locks(self, lock_dict: dict[int, asyncio.Lock]) -> int:
        """
        CRIT-NEW-01 FIX: Conservative cleanup that only removes unheld locks.

        Only removes locks when count exceeds threshold, and only removes
        locks that are not currently held. This is safe because:
        1. We only clean when we're over the threshold
        2. We only remove locks that aren't actively being used
        3. Locks can be recreated on-demand if needed again

        MED-DEEP-06 FIX: Uses snapshot for iteration and double-checks
        lock state before removal to handle race conditions.

        Args:
            lock_dict: Dictionary of locks to clean (branch or user locks).

        Returns:
            Number of locks cleaned.
        """
        if len(lock_dict) < self._cleanup_threshold:
            return 0

        cleaned = 0
        # MED-WS-13 FIX: Document cleanup ratio
        # LOW-01 FIX: Use named constant instead of magic number
        # See WSConstants.LOCK_CLEANUP_HYSTERESIS_RATIO for rationale
        target_count = int(self._cleanup_threshold * WSConstants.LOCK_CLEANUP_HYSTERESIS_RATIO)
        to_remove = len(lock_dict) - target_count

        if to_remove <= 0:
            return 0

        # MED-DEEP-06 FIX: Take snapshot of items for safe iteration
        items_snapshot = list(lock_dict.items())

        # Find unheld locks to remove (oldest first by dict order in Python 3.7+)
        keys_to_remove = []
        for key, lock in items_snapshot:
            if not lock.locked() and len(keys_to_remove) < to_remove:
                keys_to_remove.append(key)

        # MED-DEEP-06 FIX: Double-check lock state before actual removal
        for key in keys_to_remove:
            lock = lock_dict.get(key)
            # Verify key still exists and lock is still unheld
            if lock is not None and not lock.locked():
                del lock_dict[key]
                cleaned += 1

        return cleaned

    async def cleanup_stale_locks(
        self,
        active_branches: Set[int],
        active_users: Set[int],
    ) -> int:
        """
        Remove locks for branches/users with no active connections.

        This prevents unbounded growth of lock dictionaries.

        Args:
            active_branches: Set of branch IDs with active connections.
            active_users: Set of user IDs with active connections.

        Returns:
            Number of locks cleaned up.
        """
        async with self._meta_lock:
            branch_cleaned = await self._cleanup_branch_locks(active_branches)
            user_cleaned = await self._cleanup_user_locks(active_users)
            total_cleaned = branch_cleaned + user_cleaned

            if total_cleaned > 0:
                self._locks_cleaned += total_cleaned
                logger.info(
                    "Cleaned up stale locks",
                    branch_locks_cleaned=branch_cleaned,
                    user_locks_cleaned=user_cleaned,
                    total_cleaned=total_cleaned,
                )

            return total_cleaned

    async def _cleanup_branch_locks(self, active_branches: Set[int]) -> int:
        """
        Remove stale branch locks (async wrapper for compatibility).

        Only removes locks that are not currently held and have no active
        connections.

        Args:
            active_branches: Set of branch IDs with active connections.

        Returns:
            Number of branch locks cleaned.
        """
        return self._cleanup_branch_locks_sync(active_branches)

    def _cleanup_branch_locks_sync(self, active_branches: Set[int]) -> int:
        """
        HIGH-02 FIX: Sync version of branch lock cleanup.

        Args:
            active_branches: Set of branch IDs with active connections.

        Returns:
            Number of branch locks cleaned.
        """
        cleaned = 0
        stale_locks = [
            bid for bid in self._branch_locks
            if bid not in active_branches
        ]

        for bid in stale_locks:
            lock = self._branch_locks.get(bid)
            # Only remove if not currently held
            if lock and not lock.locked():
                del self._branch_locks[bid]
                cleaned += 1

        return cleaned

    async def _cleanup_user_locks(self, active_users: Set[int]) -> int:
        """
        Remove stale user locks (async wrapper for compatibility).

        Args:
            active_users: Set of user IDs with active connections.

        Returns:
            Number of user locks cleaned.
        """
        return self._cleanup_user_locks_sync(active_users)

    def _cleanup_user_locks_sync(self, active_users: Set[int]) -> int:
        """
        HIGH-02 FIX: Sync version of user lock cleanup.

        Args:
            active_users: Set of user IDs with active connections.

        Returns:
            Number of user locks cleaned.
        """
        cleaned = 0
        stale_locks = [
            uid for uid in self._user_locks
            if uid not in active_users
        ]

        for uid in stale_locks:
            lock = self._user_locks.get(uid)
            # Only remove if not currently held
            if lock and not lock.locked():
                del self._user_locks[uid]
                cleaned += 1

        return cleaned

    def get_stats(self) -> dict[str, int]:
        """Get lock manager statistics."""
        return {
            "branch_locks_count": len(self._branch_locks),
            "user_locks_count": len(self._user_locks),
            "locks_cleaned_total": self._locks_cleaned,
            "max_cached_locks": self._max_cached_locks,
            "cleanup_threshold": self._cleanup_threshold,
        }
