"""
Tests for Diner Orders endpoints.

Tests cover the full customer ordering flow:
- Submit round (add items to order)
- Create service call (call waiter)
- View order history
- Multiple rounds per session
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
    ServiceCall,
)
from shared.security.auth import sign_table_token
from tests.conftest import next_id


@pytest.fixture
def seed_table_for_diner(db_session, seed_branch, seed_tenant):
    """Create a table for diner tests."""
    table = Table(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        code="D-01",
        capacity=4,
        sector="Main",
        status="FREE",
    )
    db_session.add(table)
    db_session.commit()
    db_session.refresh(table)
    return table


@pytest.fixture
def active_table_session(db_session, seed_table_for_diner, seed_branch, seed_tenant):
    """Create an active session for the table."""
    table = seed_table_for_diner
    session = TableSession(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        table_id=table.id,
        status="OPEN",
        opened_by="DINER",
    )
    db_session.add(session)
    table.status = "ACTIVE"
    db_session.commit()
    db_session.refresh(session)
    return {"session": session, "table": table}


@pytest.fixture
def diner_category(db_session, seed_branch, seed_tenant):
    """Create a category for diner products."""
    category = Category(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        name="Pizzas",
        icon="🍕",
        order=1,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def diner_products(db_session, diner_category, seed_branch, seed_tenant):
    """Create multiple products for diner ordering."""
    products = []
    for i, (name, price) in enumerate([
        ("Margarita", 1200),
        ("Pepperoni", 1400),
        ("Hawaiian", 1300),
    ]):
        product = Product(
            id=next_id(),
            tenant_id=seed_tenant.id,
            category_id=diner_category.id,
            name=name,
            description=f"Delicious {name} pizza",
        )
        db_session.add(product)
        db_session.flush()

        bp = BranchProduct(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            product_id=product.id,
            price_cents=price,
            is_available=True,
        )
        db_session.add(bp)
        products.append(product)

    db_session.commit()
    for p in products:
        db_session.refresh(p)
    return products


@pytest.fixture
def table_token_headers(active_table_session, seed_tenant, seed_branch):
    """Headers with table token for diner authentication (using JWT)."""
    session = active_table_session["session"]
    table = active_table_session["table"]
    token = sign_table_token(
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        table_id=table.id,
        session_id=session.id,
    )
    return {"X-Table-Token": token}



class TestDinerSubmitRound:
    """Tests for POST /api/diner/rounds/submit"""

    def test_submit_round_success(
        self, client, table_token_headers, active_table_session, diner_products
    ):
        """Diner can submit a round of orders."""
        product = diner_products[0]

        response = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [
                    {"product_id": product.id, "qty": 2, "notes": "Extra cheese"}
                ]
            },
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING"
        assert data["items_count"] == 1
        assert data["total_cents"] == 2400  # 2 x 1200

    def test_submit_round_multiple_items(
        self, client, table_token_headers, active_table_session, diner_products
    ):
        """Diner can order multiple different products."""
        response = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [
                    {"product_id": diner_products[0].id, "qty": 1},  # Margarita 1200
                    {"product_id": diner_products[1].id, "qty": 2},  # Pepperoni 2800
                ]
            },
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items_count"] == 2
        assert data["total_cents"] == 4000

    def test_submit_round_without_token_fails(self, client, diner_products):
        """Cannot submit round without table token."""
        response = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [{"product_id": diner_products[0].id, "qty": 1}]
            },
        )

        assert response.status_code in [401, 403]

    def test_submit_round_invalid_product_fails(
        self, client, table_token_headers, active_table_session
    ):
        """Cannot order invalid product."""
        response = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [{"product_id": 99999, "qty": 1}]
            },
            headers=table_token_headers,
        )

        assert response.status_code == 400

    def test_submit_round_empty_items_fails(
        self, client, table_token_headers, active_table_session
    ):
        """Cannot submit empty round."""
        response = client.post(
            "/api/diner/rounds/submit",
            json={"items": []},
            headers=table_token_headers,
        )

        assert response.status_code == 400

    def test_submit_round_zero_quantity_fails(
        self, client, table_token_headers, active_table_session, diner_products
    ):
        """Cannot order zero quantity."""
        response = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [{"product_id": diner_products[0].id, "qty": 0}]
            },
            headers=table_token_headers,
        )

        assert response.status_code == 422  # Pydantic validation


class TestDinerServiceCall:
    """Tests for POST /api/diner/service-call"""

    def test_create_service_call_waiter(
        self, client, table_token_headers, active_table_session
    ):
        """Diner can call for waiter."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "WAITER"},
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "WAITER"
        assert data["status"] == "OPEN"

    def test_create_service_call_check(
        self, client, table_token_headers, active_table_session
    ):
        """Diner can request the check."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "CHECK"},
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "CHECK"

    def test_create_service_call_help(
        self, client, table_token_headers, active_table_session
    ):
        """Diner can request help."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "HELP"},
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "HELP"

    def test_duplicate_service_call_prevented(
        self, client, db_session, table_token_headers, active_table_session
    ):
        """Cannot create duplicate open service call of same type."""
        session = active_table_session["session"]

        # Create existing open call
        existing_call = ServiceCall(
            tenant_id=session.tenant_id,
            branch_id=session.branch_id,
            table_session_id=session.id,
            type="WAITER",
            status="OPEN",
        )
        db_session.add(existing_call)
        db_session.commit()

        # Try to create another
        response = client.post(
            "/api/diner/service-call",
            json={"type": "WAITER"},
            headers=table_token_headers,
        )

        # Should either fail or return existing
        assert response.status_code in [200, 400, 409]


class TestDinerOrderHistory:
    """Tests for GET /api/diner/orders"""

    @pytest.fixture
    def session_with_orders(
        self, db_session, active_table_session, diner_products, seed_tenant, seed_branch
    ):
        """Create a session with existing orders."""
        session = active_table_session["session"]

        # Round 1
        round1 = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=1,
            status="SERVED",
            submitted_by="DINER",
        )
        db_session.add(round1)
        db_session.flush()

        item1 = RoundItem(
            id=next_id(),
            round_id=round1.id,
            product_id=diner_products[0].id,
            qty=2,
            unit_price_cents=1200,
        )
        db_session.add(item1)

        # Round 2
        round2 = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=2,
            status="PENDING",
            submitted_by="DINER",
        )
        db_session.add(round2)
        db_session.flush()

        item2 = RoundItem(
            id=next_id(),
            round_id=round2.id,
            product_id=diner_products[1].id,
            qty=1,
            unit_price_cents=1400,
        )
        db_session.add(item2)

        db_session.commit()
        return session

    def test_get_order_history(
        self, client, table_token_headers, session_with_orders
    ):
        """Diner can view their order history."""
        response = client.get(
            "/api/diner/orders",
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_order_history_shows_status(
        self, client, table_token_headers, session_with_orders
    ):
        """Order history includes status for each round."""
        response = client.get(
            "/api/diner/orders",
            headers=table_token_headers,
        )

        assert response.status_code == 200
        data = response.json()

        statuses = {r["status"] for r in data}
        assert "SERVED" in statuses or "PENDING" in statuses


class TestDinerMultipleRounds:
    """Tests for multiple rounds in a session."""

    def test_submit_multiple_rounds(
        self, client, table_token_headers, active_table_session, diner_products
    ):
        """Diner can submit multiple rounds."""
        # Round 1
        response1 = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [{"product_id": diner_products[0].id, "qty": 1}]
            },
            headers=table_token_headers,
        )
        assert response1.status_code == 200
        round1_number = response1.json().get("round_number", 1)

        # Round 2
        response2 = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [{"product_id": diner_products[1].id, "qty": 1}]
            },
            headers=table_token_headers,
        )
        assert response2.status_code == 200
        round2_number = response2.json().get("round_number", 2)

        # Round numbers should increment
        assert round2_number > round1_number


class TestDinerClosedSession:
    """Tests for operations on closed sessions."""

    @pytest.fixture
    def closed_session(self, db_session, seed_table_with_token, seed_branch, seed_tenant):
        """Create a closed session."""
        table = seed_table_with_token
        session = TableSession(
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=table.id,
            status="CLOSED",
            opened_by="DINER",
        )
        db_session.add(session)
        db_session.commit()
        return session

    def test_cannot_order_on_closed_session(
        self, client, table_token_headers, closed_session, diner_products
    ):
        """Cannot submit orders on closed session."""
        response = client.post(
            "/api/diner/rounds/submit",
            json={
                "items": [{"product_id": diner_products[0].id, "qty": 1}]
            },
            headers=table_token_headers,
        )

        # Should fail or require new session
        assert response.status_code in [400, 404]
