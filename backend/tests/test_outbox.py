"""
Tests for the Outbox Pattern implementation.

Tests verify:
- OutboxEvent model and status transitions
- Outbox service for writing events atomically
- Outbox processor for publishing events
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from rest_api.models import OutboxEvent, OutboxStatus
from rest_api.services.events.outbox_service import (
    write_outbox_event,
    write_billing_outbox_event,
    write_round_outbox_event,
    write_service_call_outbox_event,
)
from rest_api.services.events.outbox_processor import (
    OutboxProcessor,
    process_pending_events_once,
)
from shared.infrastructure.events import (
    CHECK_REQUESTED,
    ROUND_SUBMITTED,
    SERVICE_CALL_CREATED,
)


class TestOutboxService:
    """Tests for outbox_service.py functions."""

    def test_write_outbox_event_creates_pending_event(self):
        """write_outbox_event should create an OutboxEvent with PENDING status."""
        mock_db = MagicMock()

        event = write_outbox_event(
            db=mock_db,
            tenant_id=1,
            event_type="TEST_EVENT",
            aggregate_type="test",
            aggregate_id=123,
            payload={"key": "value"},
        )

        # Verify event was added to session
        mock_db.add.assert_called_once()
        added_event = mock_db.add.call_args[0][0]

        assert added_event.tenant_id == 1
        assert added_event.event_type == "TEST_EVENT"
        assert added_event.aggregate_type == "test"
        assert added_event.aggregate_id == 123
        assert added_event.status == OutboxStatus.PENDING
        assert json.loads(added_event.payload) == {"key": "value"}

    def test_write_billing_outbox_event_sets_correct_fields(self):
        """write_billing_outbox_event should set billing-specific payload."""
        mock_db = MagicMock()

        event = write_billing_outbox_event(
            db=mock_db,
            tenant_id=1,
            event_type=CHECK_REQUESTED,
            check_id=456,
            branch_id=10,
            session_id=20,
            table_id=30,
            extra_data={"total_cents": 1500},
            actor_user_id=100,
            actor_role="DINER",
        )

        added_event = mock_db.add.call_args[0][0]
        payload = json.loads(added_event.payload)

        assert added_event.aggregate_type == "check"
        assert added_event.aggregate_id == 456
        assert payload["branch_id"] == 10
        assert payload["session_id"] == 20
        assert payload["table_id"] == 30
        assert payload["check_id"] == 456
        assert payload["total_cents"] == 1500
        assert payload["actor_user_id"] == 100
        assert payload["actor_role"] == "DINER"

    def test_write_round_outbox_event_sets_correct_fields(self):
        """write_round_outbox_event should set round-specific payload."""
        mock_db = MagicMock()

        event = write_round_outbox_event(
            db=mock_db,
            tenant_id=1,
            event_type=ROUND_SUBMITTED,
            round_id=789,
            branch_id=10,
            session_id=20,
            table_id=30,
            round_number=3,
            sector_id=5,
            actor_user_id=100,
            actor_role="ADMIN",
        )

        added_event = mock_db.add.call_args[0][0]
        payload = json.loads(added_event.payload)

        assert added_event.aggregate_type == "round"
        assert added_event.aggregate_id == 789
        assert payload["round_number"] == 3
        assert payload["sector_id"] == 5
        assert payload["actor_role"] == "ADMIN"

    def test_write_service_call_outbox_event_sets_correct_fields(self):
        """write_service_call_outbox_event should set service call payload."""
        mock_db = MagicMock()

        event = write_service_call_outbox_event(
            db=mock_db,
            tenant_id=1,
            event_type=SERVICE_CALL_CREATED,
            call_id=101,
            branch_id=10,
            session_id=20,
            table_id=30,
            call_type="WAITER",
            sector_id=5,
        )

        added_event = mock_db.add.call_args[0][0]
        payload = json.loads(added_event.payload)

        assert added_event.aggregate_type == "service_call"
        assert added_event.aggregate_id == 101
        assert payload["call_type"] == "WAITER"
        assert payload["sector_id"] == 5


class TestOutboxProcessor:
    """Tests for outbox_processor.py."""

    @pytest.mark.asyncio
    async def test_processor_publishes_pending_events(self):
        """Processor should fetch and publish PENDING events."""
        # Create mock event
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.tenant_id = 1
        mock_event.event_type = ROUND_SUBMITTED
        mock_event.aggregate_type = "round"
        mock_event.aggregate_id = 123
        mock_event.payload = json.dumps({
            "branch_id": 10,
            "session_id": 20,
            "table_id": 30,
            "round_number": 1,
            "actor_user_id": None,
            "actor_role": "DINER",
        })
        mock_event.status = OutboxStatus.PENDING
        mock_event.retry_count = 0

        # Mock database session
        with patch('rest_api.services.events.outbox_processor.SessionLocal') as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            # Mock query to return our event
            mock_execute = MagicMock()
            mock_execute.scalars.return_value.all.return_value = [mock_event]
            mock_db.execute.return_value = mock_execute

            # Mock Redis client and publish function
            with patch('rest_api.services.events.outbox_processor.get_redis_client') as mock_redis_client, \
                 patch('rest_api.services.events.outbox_processor.publish_round_event') as mock_publish:
                mock_redis_client.return_value = AsyncMock()
                mock_publish.return_value = None

                processor = OutboxProcessor()
                processed = await processor._process_batch()

                # Should have called publish_round_event
                mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_processor_marks_event_as_published(self):
        """Processor should mark events as PUBLISHED after successful publishing."""
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.tenant_id = 1
        mock_event.event_type = "TEST_EVENT"
        mock_event.aggregate_type = "round"
        mock_event.aggregate_id = 123
        mock_event.payload = json.dumps({
            "branch_id": 10,
            "session_id": 20,
        })
        mock_event.status = OutboxStatus.PENDING
        mock_event.retry_count = 0
        mock_event.last_error = None
        mock_event.processed_at = None

        with patch('rest_api.services.events.outbox_processor.SessionLocal') as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            mock_execute = MagicMock()
            mock_execute.scalars.return_value.all.return_value = [mock_event]
            mock_db.execute.return_value = mock_execute

            with patch('rest_api.services.events.outbox_processor.get_redis_client') as mock_redis_client, \
                 patch('rest_api.services.events.outbox_processor.publish_round_event') as mock_publish:
                mock_redis_client.return_value = AsyncMock()
                mock_publish.return_value = None

                processor = OutboxProcessor()
                await processor._process_batch()

                # Event status should be updated to PUBLISHED
                assert mock_event.status == OutboxStatus.PUBLISHED
                assert mock_event.processed_at is not None

    @pytest.mark.asyncio
    async def test_processor_retries_failed_events(self):
        """Processor should increment retry_count on failure."""
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.tenant_id = 1
        mock_event.event_type = "TEST_EVENT"
        mock_event.aggregate_type = "round"
        mock_event.aggregate_id = 123
        mock_event.payload = json.dumps({
            "branch_id": 10,
            "session_id": 20,
        })
        mock_event.status = OutboxStatus.PENDING
        mock_event.retry_count = 0
        mock_event.last_error = None

        with patch('rest_api.services.events.outbox_processor.SessionLocal') as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            mock_execute = MagicMock()
            mock_execute.scalars.return_value.all.return_value = [mock_event]
            mock_db.execute.return_value = mock_execute

            with patch('rest_api.services.events.outbox_processor.get_redis_client') as mock_redis_client:
                # Simulate Redis failure
                mock_redis_client.side_effect = Exception("Redis connection failed")

                processor = OutboxProcessor()
                await processor._process_batch()

                # Retry count should be incremented, status back to PENDING
                assert mock_event.retry_count == 1
                assert mock_event.status == OutboxStatus.PENDING

    @pytest.mark.asyncio
    async def test_processor_marks_failed_after_max_retries(self):
        """Processor should mark events as FAILED after max retries."""
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.tenant_id = 1
        mock_event.event_type = "TEST_EVENT"
        mock_event.aggregate_type = "round"
        mock_event.aggregate_id = 123
        mock_event.payload = json.dumps({
            "branch_id": 10,
            "session_id": 20,
        })
        mock_event.status = OutboxStatus.PENDING
        mock_event.retry_count = 4  # Already at max - 1
        mock_event.last_error = None

        with patch('rest_api.services.events.outbox_processor.SessionLocal') as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            mock_execute = MagicMock()
            mock_execute.scalars.return_value.all.return_value = [mock_event]
            mock_db.execute.return_value = mock_execute

            with patch('rest_api.services.events.outbox_processor.get_redis_client') as mock_redis_client:
                mock_redis_client.side_effect = Exception("Redis connection failed")

                processor = OutboxProcessor()
                await processor._process_batch()

                # After max retries, should be marked as FAILED
                assert mock_event.status == OutboxStatus.FAILED


class TestOutboxEventModel:
    """Tests for OutboxEvent model."""

    def test_outbox_status_enum_values(self):
        """OutboxStatus should have correct enum values."""
        assert OutboxStatus.PENDING.value == "PENDING"
        assert OutboxStatus.PROCESSING.value == "PROCESSING"
        assert OutboxStatus.PUBLISHED.value == "PUBLISHED"
        assert OutboxStatus.FAILED.value == "FAILED"

    def test_outbox_event_repr(self):
        """OutboxEvent should have a readable repr."""
        event = OutboxEvent()
        event.id = 123
        event.event_type = "TEST_EVENT"
        event.status = OutboxStatus.PENDING

        repr_str = repr(event)
        assert "123" in repr_str
        assert "TEST_EVENT" in repr_str
        assert "PENDING" in repr_str
