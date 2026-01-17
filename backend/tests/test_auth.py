"""
Tests for authentication endpoints.
"""

import pytest
from shared.password import hash_password, verify_password, needs_rehash


class TestPasswordHashing:
    """Test password hashing utilities."""

    def test_hash_password_returns_bcrypt_hash(self):
        """Hash should return bcrypt format."""
        hashed = hash_password("mypassword")
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        """Correct password should verify."""
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_password_incorrect(self):
        """Incorrect password should not verify."""
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_legacy_plain_text(self):
        """Legacy plain text passwords should verify for migration."""
        assert verify_password("plaintext", "plaintext") is True
        assert verify_password("wrong", "plaintext") is False

    def test_needs_rehash_plain_text(self):
        """Plain text passwords need rehashing."""
        assert needs_rehash("plaintext") is True

    def test_needs_rehash_bcrypt(self):
        """Current bcrypt hashes don't need rehashing."""
        hashed = hash_password("mypassword")
        assert needs_rehash(hashed) is False


class TestAuthEndpoints:
    """Test authentication API endpoints."""

    def test_login_success(self, client, seed_admin_user):
        """Valid credentials should return tokens."""
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "testpass123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert "user" in data
        assert data["user"]["email"] == "admin@test.com"

    def test_login_invalid_email(self, client, seed_admin_user):
        """Invalid email should fail."""
        response = client.post(
            "/api/auth/login",
            json={"email": "nonexistent@test.com", "password": "testpass123"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_invalid_password(self, client, seed_admin_user):
        """Invalid password should fail."""
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_me_authenticated(self, client, auth_headers):
        """Authenticated user can access /me endpoint."""
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@test.com"
        assert "ADMIN" in data["roles"]

    def test_me_unauthenticated(self, client):
        """Unauthenticated request to /me should fail."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_refresh_token(self, client, seed_admin_user):
        """Refresh token should return new access token."""
        # First login to get refresh token
        login_response = client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "testpass123"},
        )
        refresh_token = login_response.json()["refresh_token"]

        # Use refresh token
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"

    def test_refresh_token_invalid(self, client):
        """Invalid refresh token should fail."""
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid_token"},
        )
        assert response.status_code == 401
