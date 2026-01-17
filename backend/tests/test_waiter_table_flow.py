"""
Tests for HU-WAITER-MESA: Waiter-managed table flow endpoints.

These tests verify the complete flow for waiters managing tables:
- Activate table (CA-01)
- Submit round (CA-03)
- Request check (CA-05)
- Register manual payment (CA-06) - NO Mercado Pago
- Close table (CA-07)
- Get session summary (CA-09)
"""

import pytest
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    Product,
    Category,
    BranchProduct,
    Check,
    Payment,
    Charge,
)


@pytest.fixture
def seed_table(db_session, seed_branch, seed_tenant):
    """Create a test table."""
    table = Table(
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        code="T-01",
        capacity=4,
        sector="Main",
        status="FREE",
    )
    db_session.add(table)
    db_session.commit()
    db_session.refresh(table)
    return table


@pytest.fixture
def seed_category(db_session, seed_branch, seed_tenant):
    """Create a test category."""
    category = Category(
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        name="Test Category",
        icon="🍔",
        order=1,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def seed_product(db_session, seed_category, seed_branch, seed_tenant):
    """Create a test product with branch pricing."""
    product = Product(
        tenant_id=seed_tenant.id,
        category_id=seed_category.id,
        name="Test Burger",
        description="A delicious test burger",
        price_cents=1500,
    )
    db_session.add(product)
    db_session.flush()

    branch_product = BranchProduct(
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        product_id=product.id,
        price_cents=1500,
        is_available=True,
    )
    db_session.add(branch_product)
    db_session.commit()
    db_session.refresh(product)
    return product


class TestActivateTable:
    """Tests for POST /api/waiter/tables/{table_id}/activate"""

    def test_activate_table_success(
        self, client, waiter_auth_headers, seed_table, seed_branch
    ):
        """CA-01: Waiter can activate a free table."""
        response = client.post(
            f"/api/waiter/tables/{seed_table.id}/activate",
            json={"diner_count": 4},
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["table_id"] == seed_table.id
        assert data["diner_count"] == 4
        assert data["opened_by"] == "WAITER"
        assert "opened_by_waiter_id" in data
        assert data["status"] == "OPEN"

    def test_activate_table_already_active(
        self, client, waiter_auth_headers, db_session, seed_table, seed_branch, seed_tenant
    ):
        """Cannot activate a table that already has an active session."""
        # Create active session
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
        )
        db_session.add(session)
        seed_table.status = "ACTIVE"
        db_session.commit()

        response = client.post(
            f"/api/waiter/tables/{seed_table.id}/activate",
            json={"diner_count": 2},
            headers=waiter_auth_headers,
        )

        assert response.status_code == 400
        assert "already has an active session" in response.json()["detail"].lower()

    def test_activate_table_not_found(self, client, waiter_auth_headers):
        """Cannot activate non-existent table."""
        response = client.post(
            "/api/waiter/tables/99999/activate",
            json={"diner_count": 2},
            headers=waiter_auth_headers,
        )

        assert response.status_code == 404


class TestSubmitRound:
    """Tests for POST /api/waiter/sessions/{session_id}/rounds"""

    @pytest.fixture
    def active_session(self, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user):
        """Create an active session for round submission."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
            diner_count=2,
        )
        db_session.add(session)
        seed_table.status = "ACTIVE"
        db_session.commit()
        db_session.refresh(session)
        return session

    def test_submit_round_success(
        self, client, waiter_auth_headers, active_session, seed_product
    ):
        """CA-03: Waiter can submit a round of orders."""
        response = client.post(
            f"/api/waiter/sessions/{active_session.id}/rounds",
            json={
                "items": [
                    {"product_id": seed_product.id, "qty": 2, "notes": "No onions"},
                ]
            },
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == active_session.id
        assert data["submitted_by"] == "WAITER"
        assert data["items_count"] == 1
        assert data["total_cents"] == 3000  # 2 x 1500

    def test_submit_round_empty_items(
        self, client, waiter_auth_headers, active_session
    ):
        """Cannot submit round with no items."""
        response = client.post(
            f"/api/waiter/sessions/{active_session.id}/rounds",
            json={"items": []},
            headers=waiter_auth_headers,
        )

        assert response.status_code == 400

    def test_submit_round_invalid_product(
        self, client, waiter_auth_headers, active_session
    ):
        """Cannot submit round with invalid product ID."""
        response = client.post(
            f"/api/waiter/sessions/{active_session.id}/rounds",
            json={
                "items": [
                    {"product_id": 99999, "qty": 1},
                ]
            },
            headers=waiter_auth_headers,
        )

        assert response.status_code == 400


class TestRequestCheck:
    """Tests for POST /api/waiter/sessions/{session_id}/check"""

    @pytest.fixture
    def session_with_rounds(
        self, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user, seed_product
    ):
        """Create session with rounds for check request."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
            diner_count=2,
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=1,
            status="SERVED",
            submitted_by="WAITER",
            submitted_by_waiter_id=seed_waiter_user.id,
        )
        db_session.add(round_obj)
        db_session.flush()

        item = RoundItem(
            round_id=round_obj.id,
            product_id=seed_product.id,
            qty=2,
            unit_price_cents=1500,
        )
        db_session.add(item)

        seed_table.status = "ACTIVE"
        db_session.commit()
        db_session.refresh(session)
        return session

    def test_request_check_success(
        self, client, waiter_auth_headers, session_with_rounds
    ):
        """CA-05: Waiter can request check for session."""
        response = client.post(
            f"/api/waiter/sessions/{session_with_rounds.id}/check",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_with_rounds.id
        assert data["total_cents"] == 3000
        assert data["paid_cents"] == 0
        assert data["status"] == "REQUESTED"


class TestManualPayment:
    """Tests for POST /api/waiter/payments/manual"""

    @pytest.fixture
    def session_with_check(
        self, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user, seed_product
    ):
        """Create session with check for payment."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
            diner_count=2,
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=1,
            status="SERVED",
        )
        db_session.add(round_obj)
        db_session.flush()

        item = RoundItem(
            round_id=round_obj.id,
            product_id=seed_product.id,
            qty=2,
            unit_price_cents=1500,
        )
        db_session.add(item)
        db_session.flush()

        check = Check(
            tenant_id=seed_tenant.id,
            session_id=session.id,
            total_cents=3000,
            paid_cents=0,
            status="REQUESTED",
        )
        db_session.add(check)

        # Create charge for the item
        charge = Charge(
            tenant_id=seed_tenant.id,
            check_id=check.id,
            round_item_id=item.id,
            amount_cents=3000,
            description="Test Burger x2",
        )
        db_session.add(charge)

        seed_table.status = "PAYING"
        db_session.commit()
        db_session.refresh(check)
        return {"session": session, "check": check}

    def test_manual_payment_cash_success(
        self, client, waiter_auth_headers, session_with_check
    ):
        """CA-06: Waiter can register cash payment."""
        check = session_with_check["check"]

        response = client.post(
            "/api/waiter/payments/manual",
            json={
                "check_id": check.id,
                "amount_cents": 3000,
                "manual_method": "CASH",
            },
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["check_id"] == check.id
        assert data["amount_cents"] == 3000
        assert data["manual_method"] == "CASH"
        assert data["payment_category"] == "MANUAL"
        assert data["registered_by"] == "WAITER"
        assert data["status"] == "APPROVED"
        # Check is now fully paid
        assert data["check_remaining_cents"] == 0

    def test_manual_payment_card_success(
        self, client, waiter_auth_headers, session_with_check
    ):
        """CA-06: Waiter can register physical card payment."""
        check = session_with_check["check"]

        response = client.post(
            "/api/waiter/payments/manual",
            json={
                "check_id": check.id,
                "amount_cents": 3000,
                "manual_method": "CARD_PHYSICAL",
                "notes": "Visa ending 1234",
            },
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["manual_method"] == "CARD_PHYSICAL"

    def test_manual_payment_partial(
        self, client, waiter_auth_headers, session_with_check
    ):
        """CA-06: Waiter can register partial payment."""
        check = session_with_check["check"]

        response = client.post(
            "/api/waiter/payments/manual",
            json={
                "check_id": check.id,
                "amount_cents": 1500,
                "manual_method": "CASH",
            },
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["amount_cents"] == 1500
        assert data["check_remaining_cents"] == 1500
        assert data["check_paid_cents"] == 1500

    def test_manual_payment_invalid_check(self, client, waiter_auth_headers):
        """Cannot pay for non-existent check."""
        response = client.post(
            "/api/waiter/payments/manual",
            json={
                "check_id": 99999,
                "amount_cents": 1000,
                "manual_method": "CASH",
            },
            headers=waiter_auth_headers,
        )

        assert response.status_code == 404


class TestCloseTable:
    """Tests for POST /api/waiter/tables/{table_id}/close"""

    @pytest.fixture
    def paid_session(
        self, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user, seed_product
    ):
        """Create fully paid session for closing."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
            diner_count=2,
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            tenant_id=seed_tenant.id,
            session_id=session.id,
            total_cents=3000,
            paid_cents=3000,
            status="PAID",
        )
        db_session.add(check)

        seed_table.status = "PAYING"
        db_session.commit()
        db_session.refresh(session)
        return session

    def test_close_table_success(
        self, client, waiter_auth_headers, paid_session, seed_table
    ):
        """CA-07: Waiter can close a fully paid table."""
        response = client.post(
            f"/api/waiter/tables/{seed_table.id}/close",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["table_id"] == seed_table.id
        assert data["table_status"] == "FREE"
        assert data["session_status"] == "CLOSED"

    def test_close_table_unpaid_requires_force(
        self, client, waiter_auth_headers, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user
    ):
        """Cannot close unpaid table without force flag."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            tenant_id=seed_tenant.id,
            session_id=session.id,
            total_cents=3000,
            paid_cents=0,
            status="REQUESTED",
        )
        db_session.add(check)
        seed_table.status = "PAYING"
        db_session.commit()

        response = client.post(
            f"/api/waiter/tables/{seed_table.id}/close",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 400
        assert "not fully paid" in response.json()["detail"].lower()

    def test_close_table_force(
        self, client, waiter_auth_headers, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user
    ):
        """Can force close an unpaid table."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
        )
        db_session.add(session)
        db_session.flush()

        check = Check(
            tenant_id=seed_tenant.id,
            session_id=session.id,
            total_cents=3000,
            paid_cents=1000,
            status="REQUESTED",
        )
        db_session.add(check)
        seed_table.status = "PAYING"
        db_session.commit()

        response = client.post(
            f"/api/waiter/tables/{seed_table.id}/close",
            json={"force": True},
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["table_status"] == "FREE"


class TestSessionSummary:
    """Tests for GET /api/waiter/sessions/{session_id}/summary"""

    @pytest.fixture
    def complete_session(
        self, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user, seed_product
    ):
        """Create a session with rounds for summary."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
            diner_count=3,
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=1,
            status="SERVED",
            submitted_by="WAITER",
        )
        db_session.add(round_obj)
        db_session.flush()

        item = RoundItem(
            round_id=round_obj.id,
            product_id=seed_product.id,
            qty=3,
            unit_price_cents=1500,
        )
        db_session.add(item)

        check = Check(
            tenant_id=seed_tenant.id,
            session_id=session.id,
            total_cents=4500,
            paid_cents=1500,
            status="REQUESTED",
        )
        db_session.add(check)

        seed_table.status = "ACTIVE"
        db_session.commit()
        db_session.refresh(session)
        return session

    def test_get_session_summary(
        self, client, waiter_auth_headers, complete_session, seed_table
    ):
        """CA-09: Waiter can get session summary."""
        response = client.get(
            f"/api/waiter/sessions/{complete_session.id}/summary",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == complete_session.id
        assert data["table_id"] == seed_table.id
        assert data["diner_count"] == 3
        assert data["rounds_count"] == 1
        assert data["total_cents"] == 4500
        assert data["paid_cents"] == 1500
        assert data["opened_by"] == "WAITER"
        assert data["check_status"] == "REQUESTED"

    def test_get_session_summary_not_found(self, client, waiter_auth_headers):
        """Returns 404 for non-existent session."""
        response = client.get(
            "/api/waiter/sessions/99999/summary",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 404


class TestHybridFlow:
    """Tests for hybrid sessions (both waiter and diner actions)."""

    @pytest.fixture
    def waiter_opened_session(
        self, db_session, seed_table, seed_branch, seed_tenant, seed_waiter_user
    ):
        """Create a waiter-opened session."""
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=seed_table.id,
            status="OPEN",
            opened_by="WAITER",
            opened_by_waiter_id=seed_waiter_user.id,
            diner_count=2,
        )
        db_session.add(session)
        seed_table.status = "ACTIVE"
        db_session.commit()
        db_session.refresh(session)
        return session

    def test_is_hybrid_detection(
        self, client, waiter_auth_headers, db_session, waiter_opened_session, seed_product, seed_tenant, seed_branch
    ):
        """Session should detect hybrid flow when both waiter and diner submit rounds."""
        session = waiter_opened_session

        # Waiter submits first round
        round1 = Round(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=1,
            status="SUBMITTED",
            submitted_by="WAITER",
        )
        db_session.add(round1)
        db_session.flush()

        # Simulate diner round
        round2 = Round(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=2,
            status="SUBMITTED",
            submitted_by="DINER",
        )
        db_session.add(round2)
        db_session.commit()

        # Get summary to check is_hybrid
        response = client.get(
            f"/api/waiter/sessions/{session.id}/summary",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_hybrid"] is True
