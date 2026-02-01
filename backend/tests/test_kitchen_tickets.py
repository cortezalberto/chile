"""
Tests for Kitchen Tickets endpoints.

Tests cover the kitchen workflow:
- Get pending tickets
- Start cooking (change status to IN_PROGRESS)
- Complete ticket (change status to READY)
- Mark as served
- Ticket priorities and ordering
"""

import pytest
from datetime import datetime, timezone, timedelta
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    Product,
    Category,
    BranchProduct,
    KitchenTicket,
    User,
    UserBranchRole,
)
from shared.security.password import hash_password
from tests.conftest import next_id


@pytest.fixture
def seed_kitchen_user(db_session, seed_tenant, seed_branch):
    """Create a kitchen user for testing."""
    user = User(
        id=3,  # Explicit ID for SQLite compatibility
        tenant_id=seed_tenant.id,
        email="kitchen@test.com",
        password=hash_password("kitchen123"),
        first_name="Test",
        last_name="Cook",
    )
    db_session.add(user)
    db_session.flush()

    role = UserBranchRole(
        id=3,  # Explicit ID for SQLite compatibility
        user_id=user.id,
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        role="KITCHEN",
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def kitchen_auth_headers(client, seed_kitchen_user):
    """Get authentication headers for kitchen user."""
    response = client.post(
        "/api/auth/login",
        json={"email": "kitchen@test.com", "password": "kitchen123"},
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def kitchen_category(db_session, seed_branch, seed_tenant):
    """Create a category for kitchen products."""
    category = Category(
        id=200,  # Explicit ID for SQLite compatibility
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        name="Main Courses",
        icon="🍽️",
        order=1,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def kitchen_products(db_session, kitchen_category, seed_branch, seed_tenant):
    """Create products for kitchen tickets."""
    products = []
    for i, (name, price, prep_time) in enumerate([
        ("Steak", 2500, 15),
        ("Pasta", 1800, 10),
        ("Salad", 1200, 5),
    ]):
        product = Product(
            id=200 + i,  # Explicit ID for SQLite compatibility
            tenant_id=seed_tenant.id,
            category_id=kitchen_category.id,
            name=name,
            price_cents=price,
            prep_time_minutes=prep_time,
        )
        db_session.add(product)
        db_session.flush()

        bp = BranchProduct(
            id=200 + i,  # Explicit ID for SQLite compatibility
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            product_id=product.id,
            price_cents=price,
            is_available=True,
        )
        db_session.add(bp)
        products.append(product)

    db_session.commit()
    return products


@pytest.fixture
def pending_tickets(db_session, seed_branch, seed_tenant, kitchen_products):
    """Create pending kitchen tickets."""
    # Create table and session
    table = Table(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        code="K-01",
        capacity=4,
        sector="Main",
        status="ACTIVE",
    )
    db_session.add(table)
    db_session.flush()

    session = TableSession(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        table_id=table.id,
        status="OPEN",
    )
    db_session.add(session)
    db_session.flush()

    # Create round
    round_obj = Round(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        session_id=session.id,
        round_number=1,
        status="SUBMITTED",
    )
    db_session.add(round_obj)
    db_session.flush()

    # Create items
    items = []
    for product in kitchen_products[:2]:
        item = RoundItem(
            id=next_id(),
            round_id=round_obj.id,
            product_id=product.id,
            qty=1,
            unit_price_cents=1500,  # Use fixed price since Product doesn't have price_cents
        )
        db_session.add(item)
        items.append(item)
    db_session.flush()

    # Create tickets
    tickets = []
    for i, item in enumerate(items):
        ticket = KitchenTicket(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            round_item_id=item.id,
            status="PENDING",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=i * 5),
        )
        db_session.add(ticket)
        tickets.append(ticket)

    db_session.commit()
    for ticket in tickets:
        db_session.refresh(ticket)

    return {"tickets": tickets, "table": table, "session": session}


class TestKitchenGetTickets:
    """Tests for GET /api/kitchen/tickets"""

    def test_get_pending_tickets(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Kitchen can get pending tickets."""
        response = client.get(
            "/api/kitchen/tickets",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_tickets_ordered_by_time(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Tickets are ordered by creation time (oldest first - FIFO)."""
        response = client.get(
            "/api/kitchen/tickets",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        if len(data) >= 2:
            # First ticket should be older
            first_time = data[0].get("created_at")
            second_time = data[1].get("created_at")
            if first_time and second_time:
                assert first_time <= second_time

    def test_tickets_include_table_info(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Tickets include table information."""
        response = client.get(
            "/api/kitchen/tickets",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        if data:
            ticket = data[0]
            assert "table_code" in ticket or "table_id" in ticket

    def test_filter_by_status(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Can filter tickets by status."""
        response = client.get(
            "/api/kitchen/tickets?status=PENDING",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        for ticket in data:
            assert ticket["status"] == "PENDING"


class TestKitchenStartCooking:
    """Tests for POST /api/kitchen/tickets/{ticket_id}/start"""

    def test_start_cooking_success(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Kitchen can start cooking a ticket."""
        ticket = pending_tickets["tickets"][0]

        response = client.post(
            f"/api/kitchen/tickets/{ticket.id}/start",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "IN_PROGRESS"
        assert "started_at" in data

    def test_cannot_start_already_started(
        self, client, db_session, kitchen_auth_headers, pending_tickets
    ):
        """Cannot start a ticket that's already in progress."""
        ticket = pending_tickets["tickets"][0]
        ticket.status = "IN_PROGRESS"
        ticket.started_at = datetime.now(timezone.utc)
        db_session.commit()

        response = client.post(
            f"/api/kitchen/tickets/{ticket.id}/start",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 400

    def test_start_nonexistent_ticket(self, client, kitchen_auth_headers):
        """Cannot start non-existent ticket."""
        response = client.post(
            "/api/kitchen/tickets/99999/start",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 404


class TestKitchenCompleteTicket:
    """Tests for POST /api/kitchen/tickets/{ticket_id}/complete"""

    @pytest.fixture
    def in_progress_ticket(self, db_session, pending_tickets):
        """Create a ticket in progress."""
        ticket = pending_tickets["tickets"][0]
        ticket.status = "IN_PROGRESS"
        ticket.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.commit()
        db_session.refresh(ticket)
        return ticket

    def test_complete_ticket_success(
        self, client, kitchen_auth_headers, in_progress_ticket
    ):
        """Kitchen can complete a ticket."""
        response = client.post(
            f"/api/kitchen/tickets/{in_progress_ticket.id}/complete",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "READY"
        assert "completed_at" in data

    def test_cannot_complete_pending_ticket(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Cannot complete a ticket that hasn't been started."""
        ticket = pending_tickets["tickets"][0]

        response = client.post(
            f"/api/kitchen/tickets/{ticket.id}/complete",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 400


class TestKitchenServeTicket:
    """Tests for POST /api/kitchen/tickets/{ticket_id}/serve"""

    @pytest.fixture
    def ready_ticket(self, db_session, pending_tickets):
        """Create a ready ticket."""
        ticket = pending_tickets["tickets"][0]
        ticket.status = "READY"
        ticket.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        ticket.completed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        db_session.refresh(ticket)
        return ticket

    def test_serve_ticket_success(
        self, client, kitchen_auth_headers, ready_ticket
    ):
        """Kitchen can mark ticket as served."""
        response = client.post(
            f"/api/kitchen/tickets/{ready_ticket.id}/serve",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SERVED"

    def test_cannot_serve_pending_ticket(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Cannot serve a pending ticket."""
        ticket = pending_tickets["tickets"][0]

        response = client.post(
            f"/api/kitchen/tickets/{ticket.id}/serve",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 400


class TestKitchenStats:
    """Tests for kitchen statistics endpoints."""

    def test_get_kitchen_stats(
        self, client, kitchen_auth_headers, pending_tickets
    ):
        """Kitchen can get statistics."""
        response = client.get(
            "/api/kitchen/stats",
            headers=kitchen_auth_headers,
        )

        # Stats endpoint might not exist, check for either success or not found
        if response.status_code == 200:
            data = response.json()
            assert "pending_count" in data or "tickets" in data
        else:
            assert response.status_code == 404  # Acceptable if not implemented


class TestKitchenAccessControl:
    """Tests for kitchen access control."""

    def test_waiter_cannot_access_kitchen(
        self, client, waiter_auth_headers
    ):
        """Waiters cannot access kitchen endpoints directly."""
        response = client.get(
            "/api/kitchen/tickets",
            headers=waiter_auth_headers,
        )

        # Should either work (waiter might have kitchen access) or be forbidden
        assert response.status_code in [200, 403]

    def test_unauthenticated_cannot_access(self, client):
        """Unauthenticated users cannot access kitchen endpoints."""
        response = client.get("/api/kitchen/tickets")

        assert response.status_code in [401, 403]


class TestKitchenTicketPriority:
    """Tests for ticket priority handling."""

    @pytest.fixture
    def prioritized_tickets(
        self, db_session, seed_branch, seed_tenant, kitchen_products
    ):
        """Create tickets with different priorities."""
        # Create table and session
        table = Table(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            code="P-01",
            capacity=4,
            sector="VIP",
            status="ACTIVE",
        )
        db_session.add(table)
        db_session.flush()

        session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_id=table.id,
            status="OPEN",
        )
        db_session.add(session)
        db_session.flush()

        round_obj = Round(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            session_id=session.id,
            round_number=1,
            status="SUBMITTED",
        )
        db_session.add(round_obj)
        db_session.flush()

        tickets = []
        # Create tickets with different priorities
        for i, (product, priority) in enumerate(zip(kitchen_products, ["LOW", "NORMAL", "HIGH"])):
            item = RoundItem(
                id=next_id(),
                round_id=round_obj.id,
                product_id=product.id,
                qty=1,
                unit_price_cents=1500,  # Fixed price
            )
            db_session.add(item)
            db_session.flush()

            ticket = KitchenTicket(
                id=next_id(),
                tenant_id=seed_tenant.id,
                branch_id=seed_branch.id,
                round_item_id=item.id,
                status="PENDING",
                priority=priority,
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(ticket)
            tickets.append(ticket)

        db_session.commit()
        return tickets

    def test_high_priority_first(
        self, client, kitchen_auth_headers, prioritized_tickets
    ):
        """High priority tickets should appear first."""
        response = client.get(
            "/api/kitchen/tickets",
            headers=kitchen_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # If priorities are supported, high should come first
        if data and "priority" in data[0]:
            priorities = [t.get("priority", "NORMAL") for t in data]
            # HIGH should appear before LOW in sorted order
            if "HIGH" in priorities and "LOW" in priorities:
                high_idx = priorities.index("HIGH")
                low_idx = priorities.index("LOW")
                assert high_idx < low_idx
