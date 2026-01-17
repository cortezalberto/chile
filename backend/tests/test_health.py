"""
Tests for health check endpoints.
"""

import pytest


class TestHealthEndpoints:
    """Test health check API endpoints."""

    def test_health_check(self, client):
        """Basic health check should return healthy status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "rest-api"
