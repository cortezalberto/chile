"""
Connection Broadcaster.

Handles sending messages to WebSocket connections.
Extracted from ConnectionManager for better maintainability.

ARCH-MODULAR-02: Single Responsibility - message broadcasting only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from starlette.websockets import WebSocketState

from ws_gateway.components.core.constants import WSCloseCode, WSConstants

if TYPE_CHECKING:
    from fastapi import WebSocket
    from ws_gateway.components.connection.locks import LockManager
    from ws_gateway.components.connection.index import ConnectionIndex
    from ws_gateway.components.metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)


def is_ws_connected(ws: "WebSocket") -> bool:
    """
    Check if WebSocket is in connected state before sending.

    Starlette WebSockets have limited state visibility:
    - CONNECTING: Initial state (not observable here)
    - CONNECTED: Active connection
    - DISCONNECTED: Closed connection

    Transitional states are not exposed, so connections may appear
    connected briefly after disconnect initiated.
    """
    return (
        ws.client_state == WebSocketState.CONNECTED
        and ws.application_state == WebSocketState.CONNECTED
    )


class ConnectionBroadcaster:
    """
    Handles broadcasting messages to WebSocket connections.

    Responsibilities:
    - Send to individual connections
    - Batch broadcast to multiple connections
    - Filter by user, branch, sector, session
    - Rate limit global broadcasts

    SCALE-HIGH-01 FIX: Uses worker pool for efficient large-scale broadcasts.
    Workers process send tasks from a queue in true parallel.
    """

    # SCALE-HIGH-01: Worker pool configuration
    DEFAULT_WORKER_COUNT = 10  # Number of parallel workers
    QUEUE_MAX_SIZE = 5000  # Max pending sends before backpressure

    def __init__(
        self,
        lock_manager: "LockManager",
        index: "ConnectionIndex",
        metrics: "MetricsCollector",
        mark_dead_callback: Callable[["WebSocket"], Awaitable[None]],
        batch_size: int = 50,
        broadcast_rate_limit: int = WSConstants.MAX_BROADCASTS_PER_SECOND,
        worker_count: int | None = None,
    ) -> None:
        """
        Initialize broadcaster with dependencies.

        Args:
            lock_manager: Manages sharded locks
            index: Connection indexing
            metrics: Collects broadcast metrics
            mark_dead_callback: Callback to mark dead connections
            batch_size: Number of connections per batch (legacy mode)
            broadcast_rate_limit: Max broadcasts per second
            worker_count: Number of parallel workers (default: 10)
        """
        self._lock_manager = lock_manager
        self._index = index
        self._metrics = metrics
        self._mark_dead = mark_dead_callback
        self._batch_size = batch_size
        self._broadcast_rate_limit = broadcast_rate_limit
        
        # SCALE-HIGH-01: Worker pool
        self._worker_count = worker_count or self.DEFAULT_WORKER_COUNT
        self._queue: asyncio.Queue | None = None
        self._workers: list[asyncio.Task] = []
        self._running = False

        # Rate limiting state
        self._broadcast_timestamps: deque[float] = deque(
            maxlen=broadcast_rate_limit * 2
        )

    async def start_workers(self) -> None:
        """
        SCALE-HIGH-01 FIX: Start the worker pool.
        
        Call this during application startup (lifespan).
        Workers process send tasks from the queue in parallel.
        """
        if self._running:
            logger.warning("Worker pool already running")
            return
        
        self._queue = asyncio.Queue(maxsize=self.QUEUE_MAX_SIZE)
        self._running = True
        
        for i in range(self._worker_count):
            worker = asyncio.create_task(
                self._worker_loop(i),
                name=f"broadcast_worker_{i}"
            )
            self._workers.append(worker)
        
        logger.info(
            "Broadcast worker pool started",
            worker_count=self._worker_count,
            queue_max_size=self.QUEUE_MAX_SIZE,
        )

    async def stop_workers(self, timeout: float = 5.0) -> None:
        """
        SCALE-HIGH-01 FIX: Gracefully stop the worker pool.
        
        Call this during application shutdown.
        Waits for queue to drain or timeout.
        """
        if not self._running:
            return
        
        self._running = False
        
        # Wait for queue to drain (with timeout)
        if self._queue and not self._queue.empty():
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "Broadcast queue drain timeout",
                    remaining=self._queue.qsize(),
                )
        
        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        self._queue = None
        
        logger.info("Broadcast worker pool stopped")

    async def _worker_loop(self, worker_id: int) -> None:
        """
        SCALE-HIGH-01 FIX: Worker loop that processes send tasks.
        
        Each worker pulls tasks from the queue and sends messages.
        """
        while self._running:
            try:
                # Get task from queue (blocking with timeout)
                task = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                ws, payload, result_future = task
                
                try:
                    success = await self._send_to_connection_internal(ws, payload)
                    if result_future and not result_future.done():
                        result_future.set_result(success)
                except Exception as e:
                    if result_future and not result_future.done():
                        result_future.set_result(False)
                    logger.debug(
                        "Worker send error",
                        worker_id=worker_id,
                        error=str(e),
                    )
                finally:
                    self._queue.task_done()
                    
            except asyncio.TimeoutError:
                # No tasks, continue loop
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Worker loop error",
                    worker_id=worker_id,
                    error=str(e),
                )
                await asyncio.sleep(0.1)  # Prevent tight loop on error

    async def _send_to_connection_internal(
        self,
        ws: "WebSocket",
        payload: dict[str, Any],
    ) -> bool:
        """Internal send without queue (used by workers)."""
        if not is_ws_connected(ws):
            await self._mark_dead(ws)
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception as e:
            logger.debug("Send failed: %s", str(e))
            await self._mark_dead(ws)
            return False

    def filter_by_tenant(
        self,
        connections: list["WebSocket"],
        tenant_id: int | None,
    ) -> list["WebSocket"]:
        """
        Filter connections to only those belonging to the specified tenant.

        Args:
            connections: List of WebSocket connections to filter.
            tenant_id: Tenant ID to filter by. If None, returns all connections.

        Returns:
            Filtered list of connections belonging to the specified tenant.
        """
        return self._index.filter_by_tenant(connections, tenant_id)

    async def _send_to_connection(
        self,
        ws: "WebSocket",
        payload: dict[str, Any],
    ) -> bool:
        """
        Send to a single connection, returning success status.

        Args:
            ws: The WebSocket connection.
            payload: Message payload to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not is_ws_connected(ws):
            await self._mark_dead(ws)
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception as e:
            logger.debug("Send failed: %s", str(e))
            await self._mark_dead(ws)
            return False

    async def _broadcast_to_connections(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str = "broadcast",
    ) -> int:
        """
        Send to multiple connections in parallel.

        SCALE-HIGH-01 FIX: Uses worker pool for large broadcasts when running.
        Falls back to legacy batch mode for small broadcasts or when pool not started.

        Args:
            connections: List of WebSocket connections.
            payload: Message payload to send.
            context: Context string for logging.

        Returns:
            Number of connections that received the message.
        """
        if not connections:
            return 0

        # SCALE-HIGH-01: Use worker pool for large broadcasts
        if self._running and self._queue and len(connections) > self._batch_size:
            return await self._broadcast_via_workers(connections, payload, context)
        
        # Legacy: sequential batch processing for small broadcasts or no worker pool
        return await self._broadcast_legacy(connections, payload, context)

    async def _broadcast_via_workers(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str,
    ) -> int:
        """
        SCALE-HIGH-01 FIX: Broadcast using worker pool.

        Distributes sends across workers for true parallel processing.
        Uses futures to track completion and collect results.

        PERF-FUTURE-01 FIX: Added timeout protection to prevent future leaks
        if workers crash before setting results.
        """
        # PERF-FUTURE-01: Use get_running_loop() instead of deprecated get_event_loop()
        loop = asyncio.get_running_loop()

        # Create futures for all sends
        futures: list[asyncio.Future] = []

        for ws in connections:
            future: asyncio.Future = loop.create_future()
            futures.append(future)

            try:
                # Non-blocking put with timeout
                await asyncio.wait_for(
                    self._queue.put((ws, payload, future)),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                # Queue full, mark as failed
                if not future.done():
                    future.set_result(False)
                logger.warning(
                    "Broadcast queue full, dropping message",
                    context=context,
                    queue_size=self._queue.qsize(),
                )

        # PERF-FUTURE-01 FIX: Wait with timeout to prevent hanging forever
        # if workers crash before setting results
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*futures, return_exceptions=True),
                timeout=10.0  # 10 second timeout for entire broadcast
            )
        except asyncio.TimeoutError:
            # Some futures didn't complete - count completed ones
            logger.warning(
                "Broadcast timeout - some sends did not complete",
                context=context,
                total=len(futures),
            )
            # Cancel pending futures to prevent leaks
            for f in futures:
                if not f.done():
                    f.cancel()
            # Count what we have
            results = [f.result() if f.done() and not f.cancelled() else False for f in futures]

        # Count results
        sent = sum(1 for r in results if r is True)
        failed = len(results) - sent

        # Update metrics
        self._metrics.increment_broadcast_total_sync()
        if failed > 0:
            self._metrics.increment_broadcast_failed_sync()
            self._metrics.add_failed_recipients_sync(failed)
            logger.debug(
                "Worker broadcast completed",
                context=context,
                sent=sent,
                failed=failed,
                total=len(connections),
            )

        return sent

    async def _broadcast_legacy(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str,
    ) -> int:
        """
        Legacy broadcast using sequential batch processing.
        
        Used for small broadcasts or when worker pool is not running.
        """
        sent = 0
        failed = 0

        # Process in batches
        for i in range(0, len(connections), self._batch_size):
            batch = connections[i : i + self._batch_size]
            results = await asyncio.gather(
                *[self._send_to_connection(ws, payload) for ws in batch],
                return_exceptions=True,
            )

            # Count successes and failures
            for idx, result in enumerate(results):
                if result is True:
                    sent += 1
                else:
                    failed += 1
                    if isinstance(result, Exception):
                        logger.debug(
                            "Batch send exception",
                            context=context,
                            batch_index=idx,
                            error=str(result),
                        )

        # Update metrics
        self._metrics.increment_broadcast_total_sync()
        if failed > 0:
            self._metrics.increment_broadcast_failed_sync()
            self._metrics.add_failed_recipients_sync(failed)
            logger.debug(
                "Broadcast completed with failures",
                context=context,
                sent=sent,
                failed=failed,
                total=len(connections),
            )

        return sent

    async def send_to_user(
        self,
        user_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to all connections of a specific user."""
        connections = list(self._index.get_user_connections(user_id))
        connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"user:{user_id}"
        )

    async def send_to_branch(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to all connections in a branch.

        Tenant filtering performed inside lock to prevent race condition.
        """
        branch_lock = await self._lock_manager.get_branch_lock(branch_id)
        async with branch_lock:
            connections = list(self._index.get_branch_connections(branch_id))
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"branch:{branch_id}"
        )

    async def send_to_session(
        self,
        session_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to all connections in a table session.

        Tenant filtering performed inside lock to prevent race condition.
        """
        async with self._lock_manager.session_lock:
            connections = list(self._index.get_session_connections(session_id))
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"session:{session_id}"
        )

    async def send_to_sector(
        self,
        sector_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to all connections assigned to a sector.

        Tenant filtering performed inside lock to prevent race condition.
        """
        async with self._lock_manager.sector_lock:
            connections = list(self._index.get_sector_connections(sector_id))
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"sector:{sector_id}"
        )

    async def send_to_sectors(
        self,
        sector_ids: list[int],
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to all connections assigned to any of the given sectors.

        Tenant filtering performed inside lock to prevent race condition.
        """
        async with self._lock_manager.sector_lock:
            connections = list(self._index.get_sectors_connections(sector_ids))
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"sectors:{sector_ids}"
        )

    async def send_to_admins(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to admin/manager connections in a branch.

        Tenant filtering performed inside lock to prevent race condition.
        """
        branch_lock = await self._lock_manager.get_branch_lock(branch_id)
        async with branch_lock:
            connections = list(self._index.get_admin_connections(branch_id))
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"admins:{branch_id}"
        )

    async def send_to_waiters_only(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to NON-admin connections in a branch.

        Tenant filtering performed inside lock to prevent race condition.
        """
        branch_lock = await self._lock_manager.get_branch_lock(branch_id)
        async with branch_lock:
            connections = list(self._index.get_waiter_connections(branch_id))
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"waiters:{branch_id}"
        )

    async def send_to_kitchen(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """
        Send a message to kitchen connections in a branch.

        Tenant filtering performed inside lock to prevent race condition.
        """
        branch_lock = await self._lock_manager.get_branch_lock(branch_id)
        async with branch_lock:
            connections = list(self._index.get_kitchen_connections(branch_id))
            # Exclude admins as they receive events via send_to_admins
            connections = [c for c in connections if not self._index.is_admin(c)]
            connections = self.filter_by_tenant(connections, tenant_id)
        return await self._broadcast_to_connections(
            connections, payload, f"kitchen:{branch_id}"
        )



    async def broadcast(self, payload: dict[str, Any]) -> int:
        """
        Send a message to all connected clients.

        Rate limited to prevent broadcast spam.
        """
        now = time.time()
        window_start = now - 1.0

        # Count timestamps within window
        recent_count = sum(
            1 for ts in self._broadcast_timestamps if ts > window_start
        )

        if recent_count >= self._broadcast_rate_limit:
            logger.warning(
                "Broadcast rate limit exceeded, dropping message",
                current_rate=recent_count,
                limit=self._broadcast_rate_limit,
                payload_type=payload.get("type"),
            )
            self._metrics.increment_broadcast_rate_limited_sync()
            return 0

        # O(1) append due to deque, auto-evicts oldest if at maxlen
        self._broadcast_timestamps.append(now)

        all_connections = self._index.get_all_connections()
        return await self._broadcast_to_connections(
            list(all_connections), payload, "global"
        )
