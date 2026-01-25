"""
Lock Sequence - Enforces strict lock acquisition order to prevent deadlocks.

ARCH-AUDIT-02: New component to enforce lock ordering documented in ConnectionManager.

Lock Order (must be acquired in this order):
1. connection_counter_lock (global)
2. user_lock (per-user, by ascending user_id)
3. branch_locks (per-branch, by ascending branch_id)
4. sector_lock (global)
5. session_lock (global)
6. dead_connections_lock (global)

Usage:
    async with LockSequence(lock_manager) as seq:
        await seq.acquire_connection_counter()
        await seq.acquire_user(user_id)
        await seq.acquire_branches([1, 2, 3])  # Auto-sorted
        # ... do work ...
    # All locks released in reverse order
"""

from __future__ import annotations

import asyncio
import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LockOrder(IntEnum):
    """
    Lock acquisition order. Lower numbers must be acquired first.

    Violating this order risks deadlock when multiple coroutines
    acquire locks in different orders.
    """

    CONNECTION_COUNTER = 1
    USER = 2
    BRANCH = 3
    SECTOR = 4
    SESSION = 5
    DEAD_CONNECTIONS = 6


class DeadlockRiskError(Exception):
    """Raised when attempting to acquire locks out of order."""

    def __init__(self, attempted: LockOrder, current_max: LockOrder):
        self.attempted = attempted
        self.current_max = current_max
        super().__init__(
            f"Deadlock risk: attempting to acquire {attempted.name} (order={attempted.value}) "
            f"but already holding lock with order={current_max.value}. "
            f"Locks must be acquired in ascending order."
        )


class LockManagerProtocol(Protocol):
    """Protocol for lock manager to avoid circular imports."""

    @property
    def connection_counter_lock(self) -> asyncio.Lock: ...

    @property
    def sector_lock(self) -> asyncio.Lock: ...

    @property
    def session_lock(self) -> asyncio.Lock: ...

    @property
    def dead_connections_lock(self) -> asyncio.Lock: ...

    async def get_user_lock(self, user_id: int) -> asyncio.Lock: ...

    async def get_branch_lock(self, branch_id: int) -> asyncio.Lock: ...


class LockSequence:
    """
    Context manager that enforces strict lock acquisition order.

    Prevents deadlocks by:
    1. Tracking the highest-order lock currently held
    2. Raising DeadlockRiskError if attempting to acquire lower-order lock
    3. Auto-sorting multi-lock acquisitions (branches by ID)
    4. Releasing all locks in reverse order on exit

    Example:
        async with LockSequence(lock_manager) as seq:
            await seq.acquire_connection_counter()
            await seq.acquire_user(user_id)
            await seq.acquire_branches([3, 1, 2])  # Acquires in order: 1, 2, 3
            # ... critical section ...
        # Locks released: branches (3, 2, 1), user, connection_counter
    """

    def __init__(self, lock_manager: LockManagerProtocol, strict: bool = True):
        """
        Initialize lock sequence.

        Args:
            lock_manager: The lock manager providing locks
            strict: If True, raise on out-of-order acquisition.
                    If False, log warning but continue (testing mode).
        """
        self._lock_manager = lock_manager
        self._strict = strict
        self._current_max_order = LockOrder(0)  # No locks held
        self._held_locks: list[tuple[LockOrder, asyncio.Lock, str]] = []

    async def __aenter__(self) -> "LockSequence":
        """Enter context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Release all held locks in reverse order."""
        for order, lock, name in reversed(self._held_locks):
            try:
                lock.release()
                logger.debug(f"Released lock: {name} (order={order.value})")
            except RuntimeError as e:
                # Lock was already released (shouldn't happen)
                logger.warning(f"Failed to release lock {name}: {e}")

        self._held_locks.clear()
        self._current_max_order = LockOrder(0)

    def _check_order(self, order: LockOrder) -> None:
        """
        Check if acquiring lock would violate ordering.

        Args:
            order: The order of the lock being acquired

        Raises:
            DeadlockRiskError: If strict mode and order is violated
        """
        if order.value < self._current_max_order.value:
            if self._strict:
                raise DeadlockRiskError(order, self._current_max_order)
            else:
                logger.warning(
                    "Lock order violation (strict=False)",
                    attempted=order.name,
                    current_max=self._current_max_order.name,
                )

    async def _acquire(
        self, order: LockOrder, lock: asyncio.Lock, name: str
    ) -> None:
        """
        Acquire a lock and track it.

        Args:
            order: Lock order enum value
            lock: The asyncio.Lock to acquire
            name: Human-readable name for logging
        """
        self._check_order(order)
        await lock.acquire()
        self._held_locks.append((order, lock, name))
        if order.value > self._current_max_order.value:
            self._current_max_order = order
        logger.debug(f"Acquired lock: {name} (order={order.value})")

    # =========================================================================
    # Public acquisition methods
    # =========================================================================

    async def acquire_connection_counter(self) -> None:
        """Acquire the connection counter lock (order=1)."""
        await self._acquire(
            LockOrder.CONNECTION_COUNTER,
            self._lock_manager.connection_counter_lock,
            "connection_counter",
        )

    async def acquire_user(self, user_id: int) -> None:
        """
        Acquire lock for a specific user (order=2).

        Args:
            user_id: User ID to lock
        """
        lock = await self._lock_manager.get_user_lock(user_id)
        await self._acquire(LockOrder.USER, lock, f"user:{user_id}")

    async def acquire_users(self, user_ids: list[int]) -> None:
        """
        Acquire locks for multiple users in ascending ID order (order=2).

        Args:
            user_ids: List of user IDs to lock (will be sorted)
        """
        for user_id in sorted(user_ids):
            await self.acquire_user(user_id)

    async def acquire_branch(self, branch_id: int) -> None:
        """
        Acquire lock for a specific branch (order=3).

        Args:
            branch_id: Branch ID to lock
        """
        lock = await self._lock_manager.get_branch_lock(branch_id)
        await self._acquire(LockOrder.BRANCH, lock, f"branch:{branch_id}")

    async def acquire_branches(self, branch_ids: list[int]) -> None:
        """
        Acquire locks for multiple branches in ascending ID order (order=3).

        CRIT-AUD-02 FIX: Auto-sorts to ensure consistent ordering.

        Args:
            branch_ids: List of branch IDs to lock (will be sorted)
        """
        for branch_id in sorted(branch_ids):
            await self.acquire_branch(branch_id)

    async def acquire_sector(self) -> None:
        """Acquire the global sector lock (order=4)."""
        await self._acquire(
            LockOrder.SECTOR,
            self._lock_manager.sector_lock,
            "sector",
        )

    async def acquire_session(self) -> None:
        """Acquire the global session lock (order=5)."""
        await self._acquire(
            LockOrder.SESSION,
            self._lock_manager.session_lock,
            "session",
        )

    async def acquire_dead_connections(self) -> None:
        """Acquire the dead connections lock (order=6)."""
        await self._acquire(
            LockOrder.DEAD_CONNECTIONS,
            self._lock_manager.dead_connections_lock,
            "dead_connections",
        )

    # =========================================================================
    # Utility methods
    # =========================================================================

    @property
    def held_count(self) -> int:
        """Number of currently held locks."""
        return len(self._held_locks)

    @property
    def current_order(self) -> int:
        """Current maximum lock order held (0 if none)."""
        return self._current_max_order.value

    def is_holding(self, order: LockOrder) -> bool:
        """Check if a specific lock order is currently held."""
        return any(o == order for o, _, _ in self._held_locks)


# =============================================================================
# Convenience functions for common patterns
# =============================================================================


async def with_user_and_branches(
    lock_manager: LockManagerProtocol,
    user_id: int,
    branch_ids: list[int],
    callback,
) -> None:
    """
    Execute callback with user and branch locks held in proper order.

    Common pattern for connect/disconnect operations.

    Args:
        lock_manager: The lock manager
        user_id: User ID to lock
        branch_ids: Branch IDs to lock
        callback: Async callable to execute with locks held
    """
    async with LockSequence(lock_manager) as seq:
        await seq.acquire_user(user_id)
        await seq.acquire_branches(branch_ids)
        await callback()


async def with_counter_and_user(
    lock_manager: LockManagerProtocol,
    user_id: int,
    callback,
) -> None:
    """
    Execute callback with counter and user locks held in proper order.

    Common pattern for operations that modify total count and user state.

    Args:
        lock_manager: The lock manager
        user_id: User ID to lock
        callback: Async callable to execute with locks held
    """
    async with LockSequence(lock_manager) as seq:
        await seq.acquire_connection_counter()
        await seq.acquire_user(user_id)
        await callback()
