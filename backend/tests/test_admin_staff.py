"""
Tests for admin staff management endpoints.
"""

import pytest
from rest_api.models import User
from shared.security.password import verify_password


class TestStaffEndpoints:
    """Test admin staff CRUD operations."""

    def test_list_staff_authenticated(self, client, auth_headers, seed_admin_user):
        """Authenticated admin can list staff."""
        response = client.get("/api/admin/staff", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_staff_unauthenticated(self, client):
        """Unauthenticated request should fail."""
        response = client.get("/api/admin/staff")
        assert response.status_code == 401

    def test_create_staff_with_hashed_password(self, client, auth_headers, seed_branch, db_session):
        """Creating staff should hash the password."""
        response = client.post(
            "/api/admin/staff",
            headers=auth_headers,
            json={
                "email": "newstaff@test.com",
                "password": "staffpassword123",
                "first_name": "New",
                "last_name": "Staff",
                "branch_roles": [
                    {"branch_id": seed_branch.id, "role": "WAITER"}
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newstaff@test.com"

        # Verify password is hashed in database
        user = db_session.query(User).filter(User.email == "newstaff@test.com").first()
        assert user is not None
        assert user.password.startswith("$2b$")  # bcrypt format
        assert verify_password("staffpassword123", user.password)

    def test_create_staff_duplicate_email(self, client, auth_headers, seed_branch, seed_admin_user):
        """Creating staff with duplicate email should fail."""
        response = client.post(
            "/api/admin/staff",
            headers=auth_headers,
            json={
                "email": "admin@test.com",  # Already exists
                "password": "password123",
                "first_name": "Duplicate",
                "last_name": "User",
                "branch_roles": [
                    {"branch_id": seed_branch.id, "role": "WAITER"}
                ],
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    def test_update_staff_password_hashed(self, client, auth_headers, seed_waiter_user, db_session):
        """Updating staff password should hash it."""
        response = client.patch(
            f"/api/admin/staff/{seed_waiter_user.id}",
            headers=auth_headers,
            json={"password": "newpassword456"},
        )
        assert response.status_code == 200

        # Verify password is hashed
        db_session.refresh(seed_waiter_user)
        assert seed_waiter_user.password.startswith("$2b$")
        assert verify_password("newpassword456", seed_waiter_user.password)

    def test_delete_staff_requires_admin(self, client, waiter_auth_headers, seed_waiter_user):
        """Only admin can delete staff."""
        response = client.delete(
            f"/api/admin/staff/{seed_waiter_user.id}",
            headers=waiter_auth_headers,
        )
        assert response.status_code == 403

    def test_soft_delete_staff(self, client, auth_headers, seed_waiter_user, db_session):
        """Deleting staff soft-deletes them."""
        response = client.delete(
            f"/api/admin/staff/{seed_waiter_user.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify soft delete
        db_session.refresh(seed_waiter_user)
        assert seed_waiter_user.is_active is False

    def test_waiter_cannot_create_staff(self, client, waiter_auth_headers, seed_branch):
        """WAITER role cannot create staff."""
        response = client.post(
            "/api/admin/staff",
            headers=waiter_auth_headers,
            json={
                "email": "unauthorized@test.com",
                "password": "password123",
                "first_name": "Unauthorized",
                "last_name": "User",
                "branch_roles": [
                    {"branch_id": seed_branch.id, "role": "WAITER"}
                ],
            },
        )
        assert response.status_code == 403
