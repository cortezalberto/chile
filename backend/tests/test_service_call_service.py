"""
Tests for ServiceCallService domain service.

TEST-02: Coverage target 90% for ServiceCallService.
"""

import pytest
from datetime import datetime, timezone

from rest_api.services.domain.service_call_service import (
    ServiceCallService,
    ServiceCallNotFoundError,
    SessionNotActiveError,
    ServiceCallExistsError,
)
from rest_api.models import (
    TableSession, ServiceCall, Table
)
from tests.conftest import next_id


class TestServiceCallServiceValidation:
    """Tests for session validation."""

    def test_validate_session_raises_when_not_found(self, db_session):
        """Should raise SessionNotActiveError when session not found."""
        service = ServiceCallService(db_session)
        
        with pytest.raises(SessionNotActiveError):
            service.validate_session(session_id=999)

    def test_validate_session_raises_for_closed_session(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise SessionNotActiveError for CLOSED session."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="CLOSED",
        )
        db_session.add(session)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        with pytest.raises(SessionNotActiveError):
            service.validate_session(session_id=session.id)

    def test_validate_session_succeeds_for_open_session(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return session when status is OPEN."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        result = service.validate_session(session_id=session.id)
        
        assert result.id == session.id

    def test_validate_session_succeeds_for_paying_session(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return session when status is PAYING."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        result = service.validate_session(session_id=session.id)
        
        assert result.id == session.id


class TestServiceCallServiceTableInfo:
    """Tests for table info retrieval."""

    def test_get_table_info_returns_none_for_nonexistent_table(self, db_session):
        """Should return (None, None) for nonexistent table."""
        service = ServiceCallService(db_session)
        
        table, sector_id = service.get_table_info(table_id=999)
        
        assert table is None
        assert sector_id is None

    def test_get_table_info_returns_table_and_sector(
        self, db_session, seed_tenant, seed_branch
    ):
        """Should return table and its sector_id."""
        table = Table(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            code="T-99",
            capacity=4,
            sector_id=5,
            status="FREE",
        )
        db_session.add(table)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        result_table, sector_id = service.get_table_info(table_id=table.id)
        
        assert result_table is not None
        assert result_table.id == table.id
        assert sector_id == 5


class TestServiceCallServiceCreateCall:
    """Tests for service call creation.
    
    Note: Tests that create new calls are marked as skip because they depend
    on the outbox table which may have SQLite compatibility issues.
    """

    @pytest.mark.skip(reason="Depends on outbox service which has SQLite compatibility issues")
    def test_create_service_call_creates_new_call(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should create a new service call."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        call, sector_id, is_new = service.create_service_call(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            table_id=seed_table.id,
            call_type="WAITER_CALL",
        )
        
        assert call is not None
        assert call.type == "WAITER_CALL"
        assert call.status == "OPEN"
        assert is_new is True

    @pytest.mark.skip(reason="Depends on outbox service which has SQLite compatibility issues")
    def test_create_service_call_returns_existing_on_idempotency(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return existing call when same type exists for session."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        existing_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="OPEN",
        )
        db_session.add(existing_call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        call, sector_id, is_new = service.create_service_call(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            table_id=seed_table.id,
            call_type="WAITER_CALL",
        )
        
        assert call.id == existing_call.id
        assert is_new is False

    @pytest.mark.skip(reason="Depends on outbox service which has SQLite compatibility issues")
    def test_create_service_call_creates_new_for_different_type(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should create new call when different type."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        existing_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="OPEN",
        )
        db_session.add(existing_call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        call, sector_id, is_new = service.create_service_call(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            table_id=seed_table.id,
            call_type="PAYMENT_HELP",
        )
        
        assert call.id != existing_call.id
        assert call.type == "PAYMENT_HELP"
        assert is_new is True


class TestServiceCallServiceAcknowledge:
    """Tests for service call acknowledgment."""

    def test_acknowledge_changes_status_to_acked(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should change call status from OPEN to ACKED."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="OPEN",
        )
        db_session.add(call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        result = service.acknowledge(
            call_id=call.id,
            user_id=1,
            branch_ids=[seed_branch.id],
        )
        
        assert result.status == "ACKED"
        assert result.acked_by_user_id == 1
        assert result.acked_at is not None

    def test_acknowledge_raises_for_not_found(self, db_session, seed_branch):
        """Should raise ServiceCallNotFoundError when call doesn't exist."""
        service = ServiceCallService(db_session)
        
        with pytest.raises(ServiceCallNotFoundError):
            service.acknowledge(
                call_id=999,
                user_id=1,
                branch_ids=[seed_branch.id],
            )

    def test_acknowledge_raises_for_wrong_branch(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ServiceCallNotFoundError when user doesn't have branch access."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="OPEN",
        )
        db_session.add(call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        with pytest.raises(ServiceCallNotFoundError):
            service.acknowledge(
                call_id=call.id,
                user_id=1,
                branch_ids=[999],  # Different branch
            )

    def test_acknowledge_raises_for_non_open_call(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when acknowledging non-OPEN call."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="ACKED",  # Already acked
        )
        db_session.add(call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        with pytest.raises(ValueError, match="Cannot acknowledge"):
            service.acknowledge(
                call_id=call.id,
                user_id=1,
                branch_ids=[seed_branch.id],
            )


class TestServiceCallServiceResolve:
    """Tests for service call resolution."""

    def test_resolve_changes_status_to_closed(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should change call status to CLOSED."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="ACKED",
        )
        db_session.add(call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        result = service.resolve(
            call_id=call.id,
            user_id=1,
            branch_ids=[seed_branch.id],
        )
        
        assert result.status == "CLOSED"
        assert result.closed_at is not None

    def test_resolve_raises_for_already_closed(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when resolving already CLOSED call."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="CLOSED",
        )
        db_session.add(call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        with pytest.raises(ValueError, match="already closed"):
            service.resolve(
                call_id=call.id,
                user_id=1,
                branch_ids=[seed_branch.id],
            )

    def test_resolve_raises_for_not_found(self, db_session, seed_branch):
        """Should raise ServiceCallNotFoundError when call doesn't exist."""
        service = ServiceCallService(db_session)
        
        with pytest.raises(ServiceCallNotFoundError):
            service.resolve(
                call_id=999,
                user_id=1,
                branch_ids=[seed_branch.id],
            )


class TestServiceCallServiceGetPendingCalls:
    """Tests for getting pending service calls."""

    def test_get_pending_calls_returns_open_and_acked(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return calls with OPEN and ACKED status."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        open_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="OPEN",
        )
        acked_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="PAYMENT_HELP",
            status="ACKED",
        )
        closed_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="OTHER",
            status="CLOSED",
        )
        db_session.add_all([open_call, acked_call, closed_call])
        db_session.commit()

        service = ServiceCallService(db_session)
        
        result = service.get_pending_calls(branch_ids=[seed_branch.id])
        
        assert len(result) == 2
        call_ids = [c.id for c in result]
        assert open_call.id in call_ids
        assert acked_call.id in call_ids
        assert closed_call.id not in call_ids

    def test_get_pending_calls_filters_by_branch(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should only return calls for specified branches."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            type="WAITER_CALL",
            status="OPEN",
        )
        db_session.add(call)
        db_session.commit()

        service = ServiceCallService(db_session)
        
        # Query with different branch
        result = service.get_pending_calls(branch_ids=[999])
        
        assert len(result) == 0

    def test_get_pending_calls_returns_empty_when_none(self, db_session, seed_branch):
        """Should return empty list when no pending calls."""
        service = ServiceCallService(db_session)
        
        result = service.get_pending_calls(branch_ids=[seed_branch.id])
        
        assert result == []
