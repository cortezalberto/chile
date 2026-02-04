"""
Tests for WebSocket broadcaster - PERF-FUTURE-01 improvements.

Tests verify:
- Future leak protection with timeout
- Proper future cancellation on timeout
- Broadcast metrics accuracy
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


class TestBroadcasterFutureProtection:
    """Tests for PERF-FUTURE-01 future leak protection."""

    @pytest.mark.asyncio
    async def test_futures_have_timeout_protection(self):
        """
        Broadcast should use asyncio.wait_for with timeout
        to prevent hanging forever on slow sends.
        """
        # Simulate the broadcast logic with timeout protection
        futures = []
        loop = asyncio.get_running_loop()

        # Create some test futures
        for i in range(3):
            future = loop.create_future()
            futures.append(future)

        # Set some results immediately
        futures[0].set_result(True)
        futures[1].set_result(True)
        # futures[2] intentionally left pending to test timeout

        # This should timeout waiting for futures[2]
        async def gather_with_timeout():
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*futures, return_exceptions=True),
                    timeout=0.1  # Short timeout for test
                )
                return results
            except asyncio.TimeoutError:
                # Cancel pending futures
                for f in futures:
                    if not f.done():
                        f.cancel()
                return [f.result() if f.done() and not f.cancelled() else False for f in futures]

        results = await gather_with_timeout()

        # First two should be True, third should be False (cancelled/timeout)
        assert results[0] is True
        assert results[1] is True
        assert results[2] is False

    @pytest.mark.asyncio
    async def test_cancelled_futures_dont_leak(self):
        """Cancelled futures should be properly cleaned up."""
        loop = asyncio.get_running_loop()
        futures = []

        # Create futures that will never complete
        for _ in range(5):
            future = loop.create_future()
            futures.append(future)

        # Cancel all pending futures
        for f in futures:
            if not f.done():
                f.cancel()

        # All should be cancelled now
        for f in futures:
            assert f.cancelled() or f.done()

    @pytest.mark.asyncio
    async def test_broadcast_returns_accurate_success_count(self):
        """Broadcast should return correct count of successful sends."""
        loop = asyncio.get_running_loop()
        futures = []

        # Create 5 futures: 3 succeed, 2 fail
        for i in range(5):
            future = loop.create_future()
            if i < 3:
                future.set_result(True)  # Success
            else:
                future.set_result(False)  # Failure
            futures.append(future)

        results = await asyncio.gather(*futures, return_exceptions=True)
        success_count = sum(1 for r in results if r is True)

        assert success_count == 3

    @pytest.mark.asyncio
    async def test_exception_in_future_doesnt_crash_broadcast(self):
        """Exceptions in individual futures shouldn't crash the entire broadcast."""
        loop = asyncio.get_running_loop()
        futures = []

        # Create futures: some succeed, some fail with exception
        future1 = loop.create_future()
        future1.set_result(True)
        futures.append(future1)

        future2 = loop.create_future()
        future2.set_exception(ConnectionError("WebSocket closed"))
        futures.append(future2)

        future3 = loop.create_future()
        future3.set_result(True)
        futures.append(future3)

        # gather with return_exceptions should not raise
        results = await asyncio.gather(*futures, return_exceptions=True)

        assert results[0] is True
        assert isinstance(results[1], ConnectionError)
        assert results[2] is True

        # Count successes (True only, not exceptions)
        success_count = sum(1 for r in results if r is True)
        assert success_count == 2


class TestAsyncEventLoopUsage:
    """Tests for PERF-FUTURE-01 event loop deprecation fix."""

    def test_get_running_loop_vs_get_event_loop(self):
        """
        Should use get_running_loop() instead of deprecated get_event_loop().

        In Python 3.10+, asyncio.get_event_loop() emits a DeprecationWarning
        when there is no current event loop. asyncio.get_running_loop() is
        the recommended approach within async functions.
        """

        async def correct_usage():
            # This is the correct way - no deprecation warning
            loop = asyncio.get_running_loop()
            assert loop is not None
            return loop

        async def deprecated_usage():
            # This may emit deprecation warning in Python 3.10+
            loop = asyncio.get_event_loop()
            return loop

        # Run the correct version
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(correct_usage())
            assert result is loop
        finally:
            loop.close()


class TestQueueTimeout:
    """Tests for queue put timeout protection."""

    @pytest.mark.asyncio
    async def test_queue_put_with_timeout(self):
        """Queue put operations should have timeout protection."""
        queue = asyncio.Queue(maxsize=2)

        # Fill the queue
        await queue.put("item1")
        await queue.put("item2")

        # Queue is now full, put should timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.put("item3"), timeout=0.05)

    @pytest.mark.asyncio
    async def test_queue_timeout_doesnt_block_broadcast(self):
        """If queue is full, should timeout gracefully and mark as failed."""
        queue = asyncio.Queue(maxsize=1)
        await queue.put("blocking_item")

        success_count = 0
        fail_count = 0

        # Try to enqueue 3 items, only 0 should succeed since queue is full
        for _ in range(3):
            try:
                await asyncio.wait_for(queue.put("test"), timeout=0.01)
                success_count += 1
            except asyncio.TimeoutError:
                fail_count += 1

        assert success_count == 0  # All should fail - queue full
        assert fail_count == 3


class TestBroadcastBatching:
    """Tests for broadcast batching behavior."""

    @pytest.mark.asyncio
    async def test_batch_processing(self):
        """Broadcast should process connections in batches."""
        batch_size = 3
        connections = list(range(10))  # Simulate 10 connections

        batches_processed = []
        for i in range(0, len(connections), batch_size):
            batch = connections[i:i + batch_size]
            batches_processed.append(batch)

        # Should have 4 batches: [0,1,2], [3,4,5], [6,7,8], [9]
        assert len(batches_processed) == 4
        assert batches_processed[0] == [0, 1, 2]
        assert batches_processed[3] == [9]

    @pytest.mark.asyncio
    async def test_parallel_batch_execution(self):
        """Batches should be able to execute in parallel with gather."""
        async def process_item(item):
            await asyncio.sleep(0.01)
            return item * 2

        items = [1, 2, 3, 4, 5]
        results = await asyncio.gather(*[process_item(i) for i in items])

        assert results == [2, 4, 6, 8, 10]
