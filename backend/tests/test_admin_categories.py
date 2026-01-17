"""
Tests for admin category management endpoints.
"""

import pytest
from rest_api.models import Category


@pytest.fixture
def seed_category(db_session, seed_tenant, seed_branch):
    """Create a test category."""
    category = Category(
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        name="Test Category",
        icon="🍕",
        order=1,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


class TestCategoryEndpoints:
    """Test admin category CRUD operations."""

    def test_list_categories_authenticated(self, client, auth_headers, seed_category, seed_branch):
        """Authenticated admin can list categories."""
        response = client.get(
            f"/api/admin/categories?branch_id={seed_branch.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_categories_unauthenticated(self, client, seed_branch):
        """Unauthenticated request should fail."""
        response = client.get(f"/api/admin/categories?branch_id={seed_branch.id}")
        assert response.status_code == 401

    def test_create_category(self, client, auth_headers, seed_branch):
        """Admin can create a new category."""
        response = client.post(
            "/api/admin/categories",
            headers=auth_headers,
            json={
                "branch_id": seed_branch.id,
                "name": "New Category",
                "icon": "🍔",
                "order": 2,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Category"
        assert data["icon"] == "🍔"
        assert data["order"] == 2

    def test_create_category_waiter_forbidden(self, client, waiter_auth_headers, seed_branch):
        """WAITER role cannot create categories."""
        response = client.post(
            "/api/admin/categories",
            headers=waiter_auth_headers,
            json={
                "branch_id": seed_branch.id,
                "name": "Unauthorized Category",
                "icon": "❌",
                "order": 99,
            },
        )
        assert response.status_code == 403

    def test_update_category(self, client, auth_headers, seed_category):
        """Admin can update a category."""
        response = client.patch(
            f"/api/admin/categories/{seed_category.id}",
            headers=auth_headers,
            json={"name": "Updated Category"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Category"

    def test_delete_category(self, client, auth_headers, seed_category, db_session):
        """Admin can soft-delete a category."""
        response = client.delete(
            f"/api/admin/categories/{seed_category.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify soft delete
        db_session.refresh(seed_category)
        assert seed_category.is_active is False
