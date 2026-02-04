"""
Tests for admin_events service - PERF-DEBUG-01 and PERF-BGTASK-01 improvements.

Tests verify:
- Task names are correctly formatted for debugging
- Error callback is properly attached to tasks
- Task error handling works correctly
- PERF-BGTASK-01: BackgroundTasks integration for FastAPI request context
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from rest_api.services.events.admin_events import (
    _run_async,
    _task_error_callback,
    _publish_event,
    publish_entity_created,
    publish_entity_updated,
    publish_entity_deleted,
    publish_cascade_delete,
)


class TestTaskErrorCallback:
    """Tests for _task_error_callback function."""

    def test_callback_logs_error_on_exception(self):
        """REDIS-CRIT-02: Callback should log errors from failed tasks."""
        # Create a mock task that failed
        mock_task = MagicMock()
        mock_task.exception.return_value = ValueError("Test error")
        mock_task.get_name.return_value = "admin_event:CREATED:product:123"

        with patch('rest_api.services.events.admin_events.logger') as mock_logger:
            _task_error_callback(mock_task)

            # Should log the error
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "Admin event task failed" in call_args[0][0]
            assert call_args[1]['task_name'] == "admin_event:CREATED:product:123"
            assert call_args[1]['error'] == "Test error"

    def test_callback_handles_successful_task(self):
        """Callback should not log for successful tasks."""
        mock_task = MagicMock()
        mock_task.exception.return_value = None  # No exception

        with patch('rest_api.services.events.admin_events.logger') as mock_logger:
            _task_error_callback(mock_task)

            # Should not log any errors
            mock_logger.error.assert_not_called()

    def test_callback_handles_cancelled_task(self):
        """Callback should handle cancelled tasks gracefully."""
        mock_task = MagicMock()
        mock_task.exception.side_effect = asyncio.CancelledError()

        with patch('rest_api.services.events.admin_events.logger') as mock_logger:
            _task_error_callback(mock_task)

            # Should not log errors for cancellation
            mock_logger.error.assert_not_called()

    def test_callback_handles_invalid_state(self):
        """Callback should handle invalid state gracefully."""
        mock_task = MagicMock()
        mock_task.exception.side_effect = asyncio.InvalidStateError()

        with patch('rest_api.services.events.admin_events.logger') as mock_logger:
            _task_error_callback(mock_task)

            # Should not log errors for invalid state
            mock_logger.error.assert_not_called()


class TestTaskNames:
    """Tests for PERF-DEBUG-01 task naming pattern."""

    def test_entity_created_task_name_format(self):
        """Task name should include event type, entity type, and entity ID."""
        with patch('rest_api.services.events.admin_events._run_async') as mock_run:
            publish_entity_created(
                tenant_id=1,
                entity_type="product",
                entity_id=123,
                entity_name="Test Product",
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            task_name = call_args[1]['task_name']
            assert task_name == "admin_event:CREATED:product:123"

    def test_entity_updated_task_name_format(self):
        """Task name should include event type, entity type, and entity ID."""
        with patch('rest_api.services.events.admin_events._run_async') as mock_run:
            publish_entity_updated(
                tenant_id=1,
                entity_type="category",
                entity_id=456,
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            task_name = call_args[1]['task_name']
            assert task_name == "admin_event:UPDATED:category:456"

    def test_entity_deleted_task_name_format(self):
        """Task name should include event type, entity type, and entity ID."""
        with patch('rest_api.services.events.admin_events._run_async') as mock_run:
            publish_entity_deleted(
                tenant_id=1,
                entity_type="branch",
                entity_id=789,
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            task_name = call_args[1]['task_name']
            assert task_name == "admin_event:DELETED:branch:789"

    def test_cascade_delete_task_name_format(self):
        """Task name should include CASCADE_DELETE for cascade operations."""
        with patch('rest_api.services.events.admin_events._run_async') as mock_run:
            publish_cascade_delete(
                tenant_id=1,
                entity_type="category",
                entity_id=100,
                affected_entities=[{"type": "product", "id": 1}],
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            task_name = call_args[1]['task_name']
            assert task_name == "admin_event:CASCADE_DELETE:category:100"


class TestRunAsync:
    """Tests for _run_async helper function."""

    def test_run_async_creates_task_with_name_in_running_loop(self):
        """When in running loop, should create task with name and callback."""

        async def test_coro():
            return "result"

        async def run_test():
            with patch('asyncio.create_task') as mock_create_task:
                mock_task = MagicMock()
                mock_create_task.return_value = mock_task

                _run_async(test_coro(), task_name="test_task")

                # Should create task with name
                mock_create_task.assert_called_once()
                assert mock_create_task.call_args[1]['name'] == "test_task"

                # Should add error callback
                mock_task.add_done_callback.assert_called_once_with(_task_error_callback)

        # Run the test in an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

    def test_run_async_default_task_name(self):
        """Default task name should be 'admin_event'."""
        async def test_coro():
            return "result"

        async def run_test():
            with patch('asyncio.create_task') as mock_create_task:
                mock_task = MagicMock()
                mock_create_task.return_value = mock_task

                _run_async(test_coro())  # No task_name provided

                # Should use default name
                mock_create_task.assert_called_once()
                assert mock_create_task.call_args[1]['name'] == "admin_event"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()


class TestPublishEvent:
    """Tests for _publish_event async function."""

    @pytest.mark.asyncio
    async def test_publish_event_logs_success(self):
        """Should log successful event publishing."""
        with patch('rest_api.services.events.admin_events.get_redis_client') as mock_get_redis, \
             patch('rest_api.services.events.admin_events.publish_admin_crud_event') as mock_publish, \
             patch('rest_api.services.events.admin_events.logger') as mock_logger:

            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            await _publish_event(
                event_type="ENTITY_CREATED",
                tenant_id=1,
                branch_id=2,
                entity_type="product",
                entity_id=123,
                entity_name="Test",
            )

            # Should publish the event
            mock_publish.assert_called_once()

            # Should log success
            mock_logger.info.assert_called_once()
            assert "Admin event published" in mock_logger.info.call_args[0][0]

    @pytest.mark.asyncio
    async def test_publish_event_logs_error_on_failure(self):
        """Should log error when publishing fails."""
        with patch('rest_api.services.events.admin_events.get_redis_client') as mock_get_redis, \
             patch('rest_api.services.events.admin_events.logger') as mock_logger:

            mock_get_redis.side_effect = Exception("Redis connection failed")

            await _publish_event(
                event_type="ENTITY_CREATED",
                tenant_id=1,
                branch_id=None,
                entity_type="category",
                entity_id=1,
            )

            # Should log the error
            mock_logger.error.assert_called_once()
            assert "Failed to publish admin event" in mock_logger.error.call_args[0][0]


class TestBackgroundTasksIntegration:
    """Tests for PERF-BGTASK-01: BackgroundTasks integration."""

    def test_entity_created_uses_background_tasks_when_provided(self):
        """Should use BackgroundTasks.add_task when background_tasks is provided."""
        mock_bg_tasks = MagicMock()

        publish_entity_created(
            tenant_id=1,
            entity_type="product",
            entity_id=123,
            entity_name="Test Product",
            background_tasks=mock_bg_tasks,
        )

        # Should use add_task instead of _run_async
        mock_bg_tasks.add_task.assert_called_once()
        call_args = mock_bg_tasks.add_task.call_args
        # First arg should be _publish_event function
        assert call_args[0][0].__name__ == '_publish_event'
        # Should pass correct event_type
        assert call_args[1]['event_type'] == 'ENTITY_CREATED'
        assert call_args[1]['entity_type'] == 'product'
        assert call_args[1]['entity_id'] == 123

    def test_entity_created_falls_back_to_run_async_without_background_tasks(self):
        """Should fall back to _run_async when background_tasks is None."""
        with patch('rest_api.services.events.admin_events._run_async') as mock_run:
            publish_entity_created(
                tenant_id=1,
                entity_type="product",
                entity_id=123,
                background_tasks=None,  # Explicitly None
            )

            # Should use _run_async
            mock_run.assert_called_once()

    def test_entity_updated_uses_background_tasks_when_provided(self):
        """Should use BackgroundTasks.add_task for ENTITY_UPDATED."""
        mock_bg_tasks = MagicMock()

        publish_entity_updated(
            tenant_id=1,
            entity_type="category",
            entity_id=456,
            background_tasks=mock_bg_tasks,
        )

        mock_bg_tasks.add_task.assert_called_once()
        call_args = mock_bg_tasks.add_task.call_args
        assert call_args[1]['event_type'] == 'ENTITY_UPDATED'
        assert call_args[1]['entity_type'] == 'category'

    def test_entity_deleted_uses_background_tasks_when_provided(self):
        """Should use BackgroundTasks.add_task for ENTITY_DELETED."""
        mock_bg_tasks = MagicMock()

        publish_entity_deleted(
            tenant_id=1,
            entity_type="branch",
            entity_id=789,
            background_tasks=mock_bg_tasks,
        )

        mock_bg_tasks.add_task.assert_called_once()
        call_args = mock_bg_tasks.add_task.call_args
        assert call_args[1]['event_type'] == 'ENTITY_DELETED'
        assert call_args[1]['entity_type'] == 'branch'

    def test_cascade_delete_uses_background_tasks_when_provided(self):
        """Should use BackgroundTasks.add_task for CASCADE_DELETE."""
        mock_bg_tasks = MagicMock()
        affected = [{"type": "product", "id": 1, "name": "Test"}]

        publish_cascade_delete(
            tenant_id=1,
            entity_type="category",
            entity_id=100,
            affected_entities=affected,
            background_tasks=mock_bg_tasks,
        )

        mock_bg_tasks.add_task.assert_called_once()
        call_args = mock_bg_tasks.add_task.call_args
        assert call_args[1]['event_type'] == 'CASCADE_DELETE'
        assert call_args[1]['affected_entities'] == affected

    def test_all_parameters_passed_to_background_task(self):
        """Should pass all parameters to _publish_event via add_task."""
        mock_bg_tasks = MagicMock()

        publish_entity_created(
            tenant_id=10,
            entity_type="promotion",
            entity_id=999,
            entity_name="Summer Sale",
            branch_id=5,
            actor_user_id=42,
            background_tasks=mock_bg_tasks,
        )

        call_args = mock_bg_tasks.add_task.call_args
        assert call_args[1]['tenant_id'] == 10
        assert call_args[1]['entity_type'] == 'promotion'
        assert call_args[1]['entity_id'] == 999
        assert call_args[1]['entity_name'] == 'Summer Sale'
        assert call_args[1]['branch_id'] == 5
        assert call_args[1]['actor_user_id'] == 42
