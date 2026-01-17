"""
Tests for admin branch management endpoints.
"""

import pytest


class TestBranchEndpoints:
    """Test admin branch CRUD operations."""

    def test_list_branches_authenticated(self, client, auth_headers, seed_branch):
        """Authenticated admin can list branches."""
        response = client.get("/api/admin/branches", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Find our test branch
        test_branch = next((b for b in data if b["slug"] == "test-branch"), None)
        assert test_branch is not None
        assert test_branch["name"] == "Test Branch"

    def test_list_branches_unauthenticated(self, client):
        """Unauthenticated request should fail."""
        response = client.get("/api/admin/branches")
        assert response.status_code == 401

    def test_get_branch(self, client, auth_headers, seed_branch):
        """Can get single branch by ID."""
        response = client.get(f"/api/admin/branches/{seed_branch.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == seed_branch.id
        assert data["name"] == "Test Branch"

    def test_get_branch_not_found(self, client, auth_headers):
        """Getting non-existent branch returns 404."""
        response = client.get("/api/admin/branches/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_create_branch(self, client, auth_headers, seed_tenant):
        """Admin can create a new branch."""
        response = client.post(
            "/api/admin/branches",
            headers=auth_headers,
            json={
                "name": "New Branch",
                "slug": "new-branch",
                "address": "456 New St",
                "phone": "+1987654321",
                "opening_time": "08:00",
                "closing_time": "23:00",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Branch"
        assert data["slug"] == "new-branch"
        assert data["is_active"] is True

    def test_create_branch_duplicate_slug(self, client, auth_headers, seed_branch):
        """Creating branch with duplicate slug should fail."""
        response = client.post(
            "/api/admin/branches",
            headers=auth_headers,
            json={
                "name": "Duplicate Branch",
                "slug": "test-branch",  # Already exists
                "address": "789 Dup St",
            },
        )
        assert response.status_code == 400
        assert "slug" in response.json()["detail"].lower()

    def test_update_branch(self, client, auth_headers, seed_branch):
        """Admin can update a branch."""
        response = client.patch(
            f"/api/admin/branches/{seed_branch.id}",
            headers=auth_headers,
            json={"name": "Updated Branch Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Branch Name"

    def test_delete_branch_requires_admin(self, client, waiter_auth_headers, seed_branch):
        """Only admin can delete branches."""
        response = client.delete(
            f"/api/admin/branches/{seed_branch.id}",
            headers=waiter_auth_headers,
        )
        # WAITER role should not be able to delete
        assert response.status_code == 403

    def test_soft_delete_branch(self, client, auth_headers, seed_branch, db_session):
        """Deleting a branch soft-deletes it."""
        from rest_api.models import Branch

        response = client.delete(
            f"/api/admin/branches/{seed_branch.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify it's soft-deleted
        db_session.refresh(seed_branch)
        assert seed_branch.is_active is False
        assert seed_branch.deleted_at is not None
