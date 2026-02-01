"""
Tests for Service Call flow between Waiter and Diner.

Tests cover the complete service call lifecycle:
- Diner creates service call
- Waiter acknowledges
- Waiter resolves
- Multiple service call types
- Rate limiting
"""

import pytest
from rest_api.models import (
    Table,
    TableSession,
    ServiceCall,
)
from shared.security.auth import sign_table_token
from tests.conftest import next_id


@pytest.fixture
def service_call_table(db_session, seed_branch, seed_tenant):
    """Create a table for service call tests."""
    table = Table(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        code="SC-01",
        capacity=4,
        sector="Main",
        status="FREE",
    )
    db_session.add(table)
    db_session.commit()
    db_session.refresh(table)
    return table


@pytest.fixture
def service_call_session(db_session, service_call_table, seed_branch, seed_tenant):
    """Create an active session for service calls."""
    session = TableSession(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        table_id=service_call_table.id,
        status="OPEN",
    )
    db_session.add(session)
    service_call_table.status = "ACTIVE"
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def table_headers(service_call_session, service_call_table, seed_tenant, seed_branch):
    """Headers with table token (JWT format)."""
    token = sign_table_token(
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        table_id=service_call_table.id,
        session_id=service_call_session.id,
    )
    return {"X-Table-Token": token}


@pytest.fixture
def open_service_call(db_session, service_call_session, seed_branch, seed_tenant):
    """Create an open service call."""
    call = ServiceCall(
        id=next_id(),
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        table_session_id=service_call_session.id,
        type="WAITER",
        status="OPEN",
    )
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)
    return call


class TestDinerCreateServiceCall:
    """Tests for diner creating service calls."""

    def test_create_waiter_call(
        self, client, table_headers, service_call_session
    ):
        """Diner can create a waiter call."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "WAITER"},
            headers=table_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "WAITER"
        assert data["status"] == "OPEN"

    def test_create_check_call(
        self, client, table_headers, service_call_session
    ):
        """Diner can request the check."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "CHECK"},
            headers=table_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "CHECK"

    def test_create_help_call(
        self, client, table_headers, service_call_session
    ):
        """Diner can request help."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "HELP"},
            headers=table_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "HELP"

    def test_invalid_call_type_fails(
        self, client, table_headers, service_call_session
    ):
        """Invalid service call type fails."""
        response = client.post(
            "/api/diner/service-call",
            json={"type": "INVALID"},
            headers=table_headers,
        )

        assert response.status_code in [400, 422]


class TestWaiterViewServiceCalls:
    """Tests for waiter viewing service calls."""

    def test_get_pending_calls(
        self, client, waiter_auth_headers, open_service_call
    ):
        """Waiter can get pending service calls."""
        response = client.get(
            "/api/waiter/service-calls",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_calls_include_table_info(
        self, client, waiter_auth_headers, open_service_call
    ):
        """Service calls include table information."""
        response = client.get(
            "/api/waiter/service-calls",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        if data:
            call = data[0]
            assert "table_code" in call or "table_id" in call

    def test_only_open_and_acked_shown(
        self, client, db_session, waiter_auth_headers, service_call_session, seed_branch, seed_tenant
    ):
        """Only OPEN and ACKED calls are shown."""
        # Create OPEN call
        open_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=service_call_session.id,
            type="WAITER",
            status="OPEN",
        )
        db_session.add(open_call)

        # Create CLOSED call
        closed_call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=seed_branch.id,
            table_session_id=service_call_session.id,
            type="HELP",
            status="CLOSED",
        )
        db_session.add(closed_call)
        db_session.commit()

        response = client.get(
            "/api/waiter/service-calls",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        statuses = {call["status"] for call in data}
        assert "CLOSED" not in statuses


class TestWaiterAcknowledgeCall:
    """Tests for waiter acknowledging service calls."""

    def test_acknowledge_call(
        self, client, waiter_auth_headers, open_service_call
    ):
        """Waiter can acknowledge a service call."""
        response = client.post(
            f"/api/waiter/service-calls/{open_service_call.id}/acknowledge",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ACKED"

    def test_cannot_acknowledge_twice(
        self, client, db_session, waiter_auth_headers, open_service_call
    ):
        """Cannot acknowledge an already acknowledged call."""
        # First acknowledge
        open_service_call.status = "ACKED"
        db_session.commit()

        response = client.post(
            f"/api/waiter/service-calls/{open_service_call.id}/acknowledge",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 400

    def test_acknowledge_nonexistent_fails(self, client, waiter_auth_headers):
        """Cannot acknowledge non-existent call."""
        response = client.post(
            "/api/waiter/service-calls/99999/acknowledge",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 404


class TestWaiterResolveCall:
    """Tests for waiter resolving service calls."""

    @pytest.fixture
    def acked_service_call(self, db_session, open_service_call, seed_waiter_user):
        """Create an acknowledged service call."""
        open_service_call.status = "ACKED"
        open_service_call.acked_by_user_id = seed_waiter_user.id
        db_session.commit()
        db_session.refresh(open_service_call)
        return open_service_call

    def test_resolve_acked_call(
        self, client, waiter_auth_headers, acked_service_call
    ):
        """Waiter can resolve an acknowledged call."""
        response = client.post(
            f"/api/waiter/service-calls/{acked_service_call.id}/resolve",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CLOSED"

    def test_resolve_open_call(
        self, client, waiter_auth_headers, open_service_call
    ):
        """Waiter can resolve an open call directly (skip ack)."""
        response = client.post(
            f"/api/waiter/service-calls/{open_service_call.id}/resolve",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CLOSED"

    def test_cannot_resolve_closed(
        self, client, db_session, waiter_auth_headers, open_service_call
    ):
        """Cannot resolve an already closed call."""
        open_service_call.status = "CLOSED"
        db_session.commit()

        response = client.post(
            f"/api/waiter/service-calls/{open_service_call.id}/resolve",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 400


class TestServiceCallLifecycle:
    """Tests for the complete service call lifecycle."""

    def test_full_lifecycle(
        self, client, table_headers, waiter_auth_headers, service_call_session
    ):
        """Test complete lifecycle: create -> ack -> resolve."""
        # 1. Diner creates call
        create_resp = client.post(
            "/api/diner/service-call",
            json={"type": "WAITER"},
            headers=table_headers,
        )
        assert create_resp.status_code == 200
        call_id = create_resp.json()["id"]

        # 2. Waiter acknowledges
        ack_resp = client.post(
            f"/api/waiter/service-calls/{call_id}/acknowledge",
            headers=waiter_auth_headers,
        )
        assert ack_resp.status_code == 200
        assert ack_resp.json()["status"] == "ACKED"

        # 3. Waiter resolves
        resolve_resp = client.post(
            f"/api/waiter/service-calls/{call_id}/resolve",
            headers=waiter_auth_headers,
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "CLOSED"

        # 4. Call should not appear in pending list
        list_resp = client.get(
            "/api/waiter/service-calls",
            headers=waiter_auth_headers,
        )
        assert list_resp.status_code == 200
        call_ids = [c["id"] for c in list_resp.json()]
        assert call_id not in call_ids


class TestServiceCallBranchIsolation:
    """Tests for multi-branch isolation."""

    @pytest.fixture
    def other_branch_call(self, db_session, seed_tenant, service_call_session):
        """Create a call in a different branch."""
        from rest_api.models import Branch

        other_branch = Branch(
            id=next_id(),
            tenant_id=seed_tenant.id,
            name="Other Branch",
            slug="other-branch",
            address="789 Other St",
            phone="+1555555555",
            opening_time="09:00",
            closing_time="22:00",
        )
        db_session.add(other_branch)
        db_session.flush()

        # Need a session in the other branch
        table = Table(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=other_branch.id,
            code="OB-01",
            capacity=2,
            sector="Main",
            status="ACTIVE",
        )
        db_session.add(table)
        db_session.flush()

        other_session = TableSession(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=other_branch.id,
            table_id=table.id,
            status="OPEN",
        )
        db_session.add(other_session)
        db_session.flush()

        call = ServiceCall(
            id=next_id(),
            tenant_id=seed_tenant.id,
            branch_id=other_branch.id,
            table_session_id=other_session.id,
            type="WAITER",
            status="OPEN",
        )
        db_session.add(call)
        db_session.commit()
        db_session.refresh(call)
        return call

    def test_waiter_only_sees_own_branch(
        self, client, waiter_auth_headers, open_service_call, other_branch_call
    ):
        """Waiter only sees calls from their assigned branches."""
        response = client.get(
            "/api/waiter/service-calls",
            headers=waiter_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Should see own branch call
        call_ids = [c["id"] for c in data]
        assert open_service_call.id in call_ids

        # Should NOT see other branch call
        assert other_branch_call.id not in call_ids
