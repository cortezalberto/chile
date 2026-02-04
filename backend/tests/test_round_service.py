"""
Tests for RoundService domain service.

TEST-01: Coverage target 90% for RoundService.
"""

import pytest
from datetime import datetime, timezone

from rest_api.services.domain.round_service import (
    RoundService,
    RoundNotFoundError,
    SessionNotActiveError,
    ProductNotAvailableError,
    DuplicateRoundError,
)
from rest_api.models import (
    TableSession, Round, RoundItem, Product, BranchProduct, CartItem
)
from shared.utils.schemas import SubmitRoundRequest, RoundItemInput
from tests.conftest import next_id


class TestRoundServiceIdempotency:
    """Tests for idempotency check functionality."""

    def test_check_idempotency_returns_none_when_no_key(self, db_session):
        """Should return None when no idempotency key provided."""
        service = RoundService(db_session)
        
        result = service.check_idempotency(session_id=1, idempotency_key=None)
        
        assert result is None

    def test_check_idempotency_returns_none_when_no_existing_round(
        self, db_session, seed_tenant, seed_branch
    ):
        """Should return None when no matching round exists."""
        service = RoundService(db_session)
        
        result = service.check_idempotency(
            session_id=999,
            idempotency_key="unique-key-123",
        )
        
        assert result is None

    def test_check_idempotency_returns_existing_round(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return existing round when idempotency key matches."""
        # Create session and round with idempotency key
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        existing_round = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="PENDING",
            idempotency_key="test-key-123",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(existing_round)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.check_idempotency(
            session_id=session.id,
            idempotency_key="test-key-123",
        )
        
        assert result is not None
        assert result.id == existing_round.id

    def test_check_idempotency_ignores_canceled_rounds(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should not return canceled rounds."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        canceled_round = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="CANCELED",
            idempotency_key="test-key-456",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(canceled_round)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.check_idempotency(
            session_id=session.id,
            idempotency_key="test-key-456",
        )
        
        assert result is None


class TestRoundServiceValidation:
    """Tests for session validation."""

    def test_validate_session_raises_when_not_active(self, db_session):
        """Should raise SessionNotActiveError when session not found."""
        service = RoundService(db_session)
        
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

        service = RoundService(db_session)
        
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

        service = RoundService(db_session)
        
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

        service = RoundService(db_session)
        
        result = service.validate_session(session_id=session.id)
        
        assert result.id == session.id


class TestRoundServiceRoundOperations:
    """Tests for round lifecycle operations."""

    def test_confirm_round_changes_status_to_confirmed(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should change round status from PENDING to CONFIRMED."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(round_obj)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.confirm_round(round_id=round_obj.id, user_id=1)
        
        assert result.status == "CONFIRMED"
        assert result.confirmed_by_user_id == 1
        assert result.confirmed_at is not None

    def test_confirm_round_raises_for_non_pending_round(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when confirming non-PENDING round."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="CONFIRMED",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(round_obj)
        db_session.commit()

        service = RoundService(db_session)
        
        with pytest.raises(ValueError, match="Cannot confirm round"):
            service.confirm_round(round_id=round_obj.id, user_id=1)

    def test_confirm_round_raises_for_not_found(self, db_session):
        """Should raise RoundNotFoundError when round doesn't exist."""
        service = RoundService(db_session)
        
        with pytest.raises(RoundNotFoundError):
            service.confirm_round(round_id=999, user_id=1)

    def test_cancel_round_changes_status_to_canceled(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should change round status to CANCELED."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(round_obj)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.cancel_round(round_id=round_obj.id, user_id=1)
        
        assert result.status == "CANCELED"
        assert result.canceled_at is not None

    def test_cancel_round_raises_for_submitted_round(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when canceling SUBMITTED round."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="SUBMITTED",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(round_obj)
        db_session.commit()

        service = RoundService(db_session)
        
        with pytest.raises(ValueError, match="Cannot cancel round"):
            service.cancel_round(round_id=round_obj.id, user_id=1)

    def test_submit_to_kitchen_changes_status(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should change round status to SUBMITTED."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="CONFIRMED",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(round_obj)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.submit_to_kitchen(round_id=round_obj.id, user_id=1)
        
        assert result.status == "SUBMITTED"
        assert result.sent_to_kitchen_at is not None


class TestRoundServiceGetRounds:
    """Tests for getting session rounds."""

    def test_get_session_rounds_returns_empty_for_no_rounds(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return empty list when session has no rounds."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.get_session_rounds(session_id=session.id)
        
        assert result == []

    def test_get_session_rounds_returns_rounds_with_items(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should return rounds with their items."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(round_obj)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Burger",
            description="Delicious test burger",
        )
        db_session.add(product)
        db_session.flush()

        round_item = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=2,
            unit_price_cents=1500,
            notes="No onions",
        )
        db_session.add(round_item)
        db_session.commit()

        service = RoundService(db_session)
        
        result = service.get_session_rounds(session_id=session.id)
        
        assert len(result) == 1
        assert result[0].id == round_obj.id
        assert result[0].round_number == 1
        assert len(result[0].items) == 1
        assert result[0].items[0].product_name == "Test Burger"
        assert result[0].items[0].qty == 2
