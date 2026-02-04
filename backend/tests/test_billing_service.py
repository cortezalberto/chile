"""
Tests for BillingService domain service.

TEST-03: Coverage target 90% for BillingService.
"""

import pytest
from datetime import datetime, timezone

from rest_api.services.domain.billing_service import (
    BillingService,
    CheckNotFoundError,
    SessionNotActiveError,
    CheckAlreadyExistsError,
)
from rest_api.models import (
    TableSession, Round, RoundItem, Product, Check, Payment
)
from tests.conftest import next_id


class TestBillingServiceSessionTotal:
    """Tests for session total calculation."""

    def test_calculate_session_total_returns_zero_for_no_rounds(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return 0 when session has no rounds."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = BillingService(db_session)
        
        result = service.calculate_session_total(session_id=session.id)
        
        assert result == 0

    def test_calculate_session_total_sums_items(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should sum all items from non-canceled rounds."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Burger",
            description="Delicious",
        )
        db_session.add(product)
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
        db_session.flush()

        # Add items: 2 items at 1000 each = 2000, 3 items at 500 each = 1500
        item1 = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=2,
            unit_price_cents=1000,
        )
        item2 = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=3,
            unit_price_cents=500,
        )
        db_session.add_all([item1, item2])
        db_session.commit()

        service = BillingService(db_session)
        
        result = service.calculate_session_total(session_id=session.id)
        
        # 2 * 1000 + 3 * 500 = 2000 + 1500 = 3500
        assert result == 3500

    def test_calculate_session_total_excludes_canceled_rounds(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should not include items from CANCELED rounds."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Burger",
            description="Delicious",
        )
        db_session.add(product)
        db_session.flush()

        # Confirmed round
        confirmed_round = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=1,
            status="CONFIRMED",
            submitted_at=datetime.now(timezone.utc),
        )
        # Canceled round
        canceled_round = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            round_number=2,
            status="CANCELED",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([confirmed_round, canceled_round])
        db_session.flush()

        # Items in confirmed round
        item1 = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=confirmed_round.id,
            product_id=product.id,
            qty=1,
            unit_price_cents=1000,
        )
        # Items in canceled round (should be excluded)
        item2 = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=canceled_round.id,
            product_id=product.id,
            qty=5,
            unit_price_cents=2000,
        )
        db_session.add_all([item1, item2])
        db_session.commit()

        service = BillingService(db_session)
        
        result = service.calculate_session_total(session_id=session.id)
        
        # Only 1 * 1000 = 1000, not including canceled round
        assert result == 1000


class TestBillingServiceGetSessionTotal:
    """Tests for get session total with check info."""

    def test_get_session_total_returns_info_without_check(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return session info when no check exists."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = BillingService(db_session)
        
        result = service.get_session_total(session_id=session.id)
        
        assert result["session_id"] == session.id
        assert result["total_cents"] == 0
        assert result["paid_cents"] == 0
        assert result["check_id"] is None
        assert result["check_status"] is None

    def test_get_session_total_includes_check_info(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should include check info when check exists."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=5000,
            paid_cents=2000,
            status="OPEN",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        result = service.get_session_total(session_id=session.id)
        
        assert result["check_id"] == check.id
        assert result["check_status"] == "OPEN"
        assert result["paid_cents"] == 2000


class TestBillingServiceGetOrCreateCheck:
    """Tests for check creation."""

    @pytest.mark.skip(reason="BigInteger PK doesn't auto-increment in SQLite")
    def test_get_or_create_check_creates_new_check(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should create new check when none exists."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = BillingService(db_session)
        
        check, is_new = service.get_or_create_check(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
        )
        
        assert check is not None
        assert is_new is True
        assert check.status == "OPEN"
        assert check.paid_cents == 0

    def test_get_or_create_check_returns_existing(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should return existing check when one exists."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        existing_check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=1000,
            paid_cents=0,
            status="OPEN",
        )
        db_session.add(existing_check)
        db_session.commit()

        service = BillingService(db_session)
        
        check, is_new = service.get_or_create_check(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
        )
        
        assert check.id == existing_check.id
        assert is_new is False


class TestBillingServiceRecordPayment:
    """Tests for payment recording."""

    @pytest.mark.skip(reason="BigInteger PK doesn't auto-increment in SQLite")
    def test_record_payment_creates_payment(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should create payment record."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=5000,
            paid_cents=0,
            status="OPEN",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        payment = service.record_payment(
            check_id=check.id,
            provider="CASH",
            amount_cents=2000,
        )
        
        assert payment is not None
        assert payment.amount_cents == 2000
        assert payment.status == "APPROVED"
        assert payment.provider == "CASH"

    @pytest.mark.skip(reason="BigInteger PK doesn't auto-increment in SQLite")
    def test_record_payment_updates_check_paid_cents(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should update check paid_cents."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=5000,
            paid_cents=1000,
            status="OPEN",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        service.record_payment(
            check_id=check.id,
            provider="CASH",
            amount_cents=2000,
        )
        
        db_session.refresh(check)
        assert check.paid_cents == 3000

    @pytest.mark.skip(reason="BigInteger PK doesn't auto-increment in SQLite")
    def test_record_payment_marks_check_as_paid_when_complete(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should mark check as PAID when fully paid."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=5000,
            paid_cents=3000,
            status="OPEN",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        service.record_payment(
            check_id=check.id,
            provider="CASH",
            amount_cents=2000,
        )
        
        db_session.refresh(check)
        assert check.status == "PAID"
        assert check.paid_at is not None

    def test_record_payment_raises_for_not_found(self, db_session):
        """Should raise CheckNotFoundError when check doesn't exist."""
        service = BillingService(db_session)
        
        with pytest.raises(CheckNotFoundError):
            service.record_payment(
                check_id=999,
                provider="CASH",
                amount_cents=1000,
            )


class TestBillingServiceGetCheckDetail:
    """Tests for check detail retrieval."""

    def test_get_check_detail_raises_when_no_check(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise CheckNotFoundError when no check exists."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = BillingService(db_session)
        
        with pytest.raises(CheckNotFoundError):
            service.get_check_detail(
                session_id=session.id,
                table_id=seed_table.id,
            )

    def test_get_check_detail_returns_items_and_payments(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should return check with items and payments."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Burger",
            description="Delicious",
        )
        db_session.add(product)
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
        db_session.flush()

        item = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=2,
            unit_price_cents=1500,
        )
        db_session.add(item)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=3000,
            paid_cents=1000,
            status="OPEN",
        )
        db_session.add(check)
        db_session.flush()

        payment = Payment(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            check_id=check.id,
            provider="CASH",
            amount_cents=1000,
            status="APPROVED",
        )
        db_session.add(payment)
        db_session.commit()

        service = BillingService(db_session)
        
        result = service.get_check_detail(
            session_id=session.id,
            table_id=seed_table.id,
        )
        
        assert result.id == check.id
        assert result.total_cents == 3000
        assert result.paid_cents == 1000
        assert result.remaining_cents == 2000
        assert len(result.items) == 1
        assert result.items[0].product_name == "Test Burger"
        assert len(result.payments) == 1
        assert result.payments[0].amount_cents == 1000


# ============================================================================
# TEST-03-EXT: Extended tests for request_check and record_manual_payment
# ============================================================================

class TestBillingServiceRequestCheck:
    """Tests for request_check method (waiter flow)."""

    def test_request_check_creates_new_check(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should create a new check with REQUESTED status."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Item",
            description="Test",
        )
        db_session.add(product)
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
        db_session.flush()

        item = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=2,
            unit_price_cents=1500,
        )
        db_session.add(item)
        db_session.commit()

        service = BillingService(db_session)
        
        check, items_count, is_new = service.request_check(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
        )
        
        assert is_new is True
        assert check.status == "REQUESTED"
        assert check.total_cents == 3000  # 2 * 1500
        assert check.paid_cents == 0
        assert items_count == 2

    def test_request_check_returns_existing_check(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should return existing check without creating new one."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Item",
            description="Test",
        )
        db_session.add(product)
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
        db_session.flush()

        item = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=1,
            unit_price_cents=1000,
        )
        db_session.add(item)
        db_session.flush()

        existing_check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=1000,
            paid_cents=0,
            status="REQUESTED",
        )
        db_session.add(existing_check)
        db_session.commit()

        service = BillingService(db_session)
        
        check, items_count, is_new = service.request_check(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
        )
        
        assert is_new is False
        assert check.id == existing_check.id

    def test_request_check_raises_error_for_empty_session(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when session has no items."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.commit()

        service = BillingService(db_session)
        
        with pytest.raises(ValueError) as exc_info:
            service.request_check(
                tenant_id=seed_tenant.id,
                branch_id=seed_branch.id,
                session_id=session.id,
            )
        
        assert "No items to bill" in str(exc_info.value)

    def test_request_check_updates_session_status_to_paying(
        self, db_session, seed_tenant, seed_branch, seed_table, seed_category
    ):
        """Should update session status to PAYING when creating check."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=seed_category.id,
            name="Test Item",
            description="Test",
        )
        db_session.add(product)
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
        db_session.flush()

        item = RoundItem(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_id=round_obj.id,
            product_id=product.id,
            qty=1,
            unit_price_cents=1000,
        )
        db_session.add(item)
        db_session.commit()

        service = BillingService(db_session)
        service.request_check(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
        )
        
        db_session.refresh(session)
        assert session.status == "PAYING"


class TestBillingServiceRecordManualPayment:
    """Tests for record_manual_payment method (waiter manual payments)."""

    def test_record_manual_payment_creates_payment(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should create a payment record for manual cash payment."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=5000,
            paid_cents=0,
            status="REQUESTED",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        payment, updated_check = service.record_manual_payment(
            check_id=check.id,
            amount_cents=2000,
            manual_method="CASH",
            waiter_id=1,
            branch_ids=[seed_branch.id],
        )
        
        assert payment.amount_cents == 2000
        assert payment.provider == "CASH"
        assert payment.status == "APPROVED"
        assert payment.payment_category == "MANUAL"
        assert updated_check.paid_cents == 2000
        assert updated_check.status == "IN_PAYMENT"

    def test_record_manual_payment_marks_check_paid_when_complete(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should mark check as PAID when fully paid."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=3000,
            paid_cents=0,
            status="REQUESTED",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        payment, updated_check = service.record_manual_payment(
            check_id=check.id,
            amount_cents=3000,
            manual_method="CARD_PHYSICAL",
            waiter_id=1,
            branch_ids=[seed_branch.id],
        )
        
        assert updated_check.status == "PAID"
        assert updated_check.paid_cents == 3000

    def test_record_manual_payment_raises_error_for_invalid_check(
        self, db_session, seed_branch
    ):
        """Should raise CheckNotFoundError for non-existent check."""
        service = BillingService(db_session)
        
        with pytest.raises(CheckNotFoundError):
            service.record_manual_payment(
                check_id=99999,
                amount_cents=1000,
                manual_method="CASH",
                waiter_id=1,
                branch_ids=[seed_branch.id],
            )

    def test_record_manual_payment_raises_error_for_wrong_branch(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise CheckNotFoundError when waiter has no access to branch."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=3000,
            paid_cents=0,
            status="REQUESTED",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        with pytest.raises(CheckNotFoundError):
            service.record_manual_payment(
                check_id=check.id,
                amount_cents=1000,
                manual_method="CASH",
                waiter_id=1,
                branch_ids=[99999],  # Wrong branch
            )

    def test_record_manual_payment_raises_error_for_overpayment(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when payment exceeds remaining balance."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="PAYING",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=2000,
            paid_cents=1500,
            status="IN_PAYMENT",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        with pytest.raises(ValueError) as exc_info:
            service.record_manual_payment(
                check_id=check.id,
                amount_cents=1000,  # Only 500 remaining
                manual_method="CASH",
                waiter_id=1,
                branch_ids=[seed_branch.id],
            )
        
        assert "exceeds remaining balance" in str(exc_info.value)

    def test_record_manual_payment_raises_error_for_paid_check(
        self, db_session, seed_tenant, seed_branch, seed_table
    ):
        """Should raise ValueError when check is already paid."""
        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="CLOSED",
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=session.id,
            total_cents=3000,
            paid_cents=3000,
            status="PAID",
        )
        db_session.add(check)
        db_session.commit()

        service = BillingService(db_session)
        
        with pytest.raises(ValueError) as exc_info:
            service.record_manual_payment(
                check_id=check.id,
                amount_cents=500,
                manual_method="CASH",
                waiter_id=1,
                branch_ids=[seed_branch.id],
            )
        
        assert "Cannot pay check with status" in str(exc_info.value)
