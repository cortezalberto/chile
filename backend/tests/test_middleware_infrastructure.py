"""
Tests for middleware and infrastructure components.

TEST-04: Coverage target 80% for middleware/infrastructure.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient

from rest_api.core.middlewares import (
    SecurityHeadersMiddleware,
    ContentTypeValidationMiddleware,
    register_middlewares,
)
from shared.infrastructure.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
    get_request_id,
    request_id_var,
)
from shared.infrastructure.db import safe_commit


# =============================================================================
# SecurityHeadersMiddleware Tests
# =============================================================================

class TestSecurityHeadersMiddleware:
    """Tests for security headers middleware."""

    @pytest.fixture
    def app_with_security_headers(self):
        """Create a test app with security headers middleware."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "ok"}
        
        return app

    def test_adds_x_content_type_options(self, app_with_security_headers):
        """Should add X-Content-Type-Options: nosniff header."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")
        
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_adds_x_frame_options(self, app_with_security_headers):
        """Should add X-Frame-Options: DENY header."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")
        
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_adds_x_xss_protection(self, app_with_security_headers):
        """Should add X-XSS-Protection header."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")
        
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_adds_referrer_policy(self, app_with_security_headers):
        """Should add Referrer-Policy header."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")
        
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_adds_permissions_policy(self, app_with_security_headers):
        """Should add Permissions-Policy header."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")
        
        assert "geolocation=()" in response.headers.get("Permissions-Policy", "")

    def test_adds_content_security_policy(self, app_with_security_headers):
        """Should add Content-Security-Policy header."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")
        
        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp

    def test_adds_hsts_in_production(self):
        """Should add HSTS header only in production."""
        with patch("shared.config.settings.settings") as mock_settings:
            mock_settings.environment = "production"
            
            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware)
            
            @app.get("/test")
            def test_endpoint():
                return {"message": "ok"}
            
            client = TestClient(app)
            response = client.get("/test")
            
            hsts = response.headers.get("Strict-Transport-Security", "")
            assert "max-age=31536000" in hsts

    def test_no_hsts_in_development(self):
        """Should not add HSTS header in development."""
        with patch("shared.config.settings.settings") as mock_settings:
            mock_settings.environment = "development"
            
            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware)
            
            @app.get("/test")
            def test_endpoint():
                return {"message": "ok"}
            
            client = TestClient(app)
            response = client.get("/test")
            
            # In development mode, HSTS should not be present
            hsts = response.headers.get("Strict-Transport-Security", "")
            assert "max-age=" not in hsts


# =============================================================================
# ContentTypeValidationMiddleware Tests
# =============================================================================

class TestContentTypeValidationMiddleware:
    """Tests for content-type validation middleware."""

    @pytest.fixture
    def app_with_content_validation(self):
        """Create a test app with content-type validation middleware."""
        app = FastAPI()
        app.add_middleware(ContentTypeValidationMiddleware)
        
        @app.post("/test")
        def post_endpoint(data: dict = None):
            return {"message": "ok"}
        
        @app.get("/test")
        def get_endpoint():
            return {"message": "ok"}
        
        @app.post("/api/billing/webhook/mp")
        def webhook_endpoint():
            return {"message": "ok"}
        
        return app

    def test_allows_json_content_type(self, app_with_content_validation):
        """Should allow application/json content type."""
        client = TestClient(app_with_content_validation)
        response = client.post(
            "/test",
            json={"key": "value"},
        )
        
        # Should not return 415
        assert response.status_code != 415

    def test_allows_form_urlencoded(self, app_with_content_validation):
        """Should allow form-urlencoded content type."""
        client = TestClient(app_with_content_validation)
        response = client.post(
            "/test",
            data={"key": "value"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        # Should not return 415
        assert response.status_code != 415

    def test_rejects_unsupported_content_type(self, app_with_content_validation):
        """Should reject unsupported content types with 415."""
        client = TestClient(app_with_content_validation)
        response = client.post(
            "/test",
            content="some data",
            headers={"Content-Type": "text/plain"},
        )
        
        assert response.status_code == 415
        assert "Unsupported Media Type" in response.json()["detail"]

    def test_allows_get_without_content_type(self, app_with_content_validation):
        """Should allow GET requests without content type validation."""
        client = TestClient(app_with_content_validation)
        response = client.get("/test")
        
        assert response.status_code == 200

    def test_exempts_webhook_endpoints(self, app_with_content_validation):
        """Should exempt webhook endpoints from validation."""
        client = TestClient(app_with_content_validation)
        response = client.post(
            "/api/billing/webhook/mp",
            content="webhook data",
            headers={"Content-Type": "text/plain"},
        )
        
        # Should not return 415 for exempt paths
        assert response.status_code != 415


# =============================================================================
# CorrelationIdMiddleware Tests
# =============================================================================

class TestCorrelationIdMiddleware:
    """Tests for correlation ID middleware."""

    @pytest.fixture
    def app_with_correlation(self):
        """Create a test app with correlation ID middleware."""
        app = FastAPI()
        app.add_middleware(CorrelationIdMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"request_id": get_request_id()}
        
        return app

    def test_generates_request_id_when_not_provided(self, app_with_correlation):
        """Should generate a new request ID when not provided."""
        client = TestClient(app_with_correlation)
        response = client.get("/test")
        
        # Response should have X-Request-ID header
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) == 36  # UUID v4 length

    def test_uses_provided_request_id(self, app_with_correlation):
        """Should use the provided X-Request-ID header."""
        client = TestClient(app_with_correlation)
        custom_id = "my-custom-request-id-12345"
        response = client.get(
            "/test",
            headers={"X-Request-ID": custom_id},
        )
        
        assert response.headers.get("X-Request-ID") == custom_id

    def test_returns_request_id_in_response(self, app_with_correlation):
        """Should return request ID in response headers."""
        client = TestClient(app_with_correlation)
        response = client.get("/test")
        
        assert "X-Request-ID" in response.headers


# =============================================================================
# CorrelationIdFilter Tests
# =============================================================================

class TestCorrelationIdFilter:
    """Tests for correlation ID logging filter."""

    def test_adds_request_id_to_log_record(self):
        """Should add request_id attribute to log record."""
        filter_obj = CorrelationIdFilter()
        
        # Set a request ID
        token = request_id_var.set("test-request-123")
        
        try:
            # Create a mock log record
            record = MagicMock()
            
            result = filter_obj.filter(record)
            
            assert result is True
            assert record.request_id == "test-request-123"
        finally:
            request_id_var.reset(token)

    def test_uses_dash_when_no_request_id(self):
        """Should use '-' when no request ID is set."""
        filter_obj = CorrelationIdFilter()
        
        # Make sure no request ID is set
        token = request_id_var.set("")
        
        try:
            record = MagicMock()
            
            result = filter_obj.filter(record)
            
            assert result is True
            assert record.request_id == "-"
        finally:
            request_id_var.reset(token)


# =============================================================================
# safe_commit Tests
# =============================================================================

class TestSafeCommit:
    """Tests for safe_commit utility."""

    def test_commits_successfully(self):
        """Should commit when no error occurs."""
        mock_db = MagicMock()
        
        safe_commit(mock_db)
        
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_rollbacks_on_error(self):
        """Should rollback when commit fails."""
        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            safe_commit(mock_db)
        
        mock_db.rollback.assert_called_once()

    def test_reraises_original_exception(self):
        """Should re-raise the original exception after rollback."""
        mock_db = MagicMock()
        
        class CustomDBError(Exception):
            pass
        
        mock_db.commit.side_effect = CustomDBError("Custom error")
        
        with pytest.raises(CustomDBError):
            safe_commit(mock_db)


# =============================================================================
# register_middlewares Tests
# =============================================================================

class TestRegisterMiddlewares:
    """Tests for middleware registration."""

    def test_registers_all_middlewares(self):
        """Should register all security middlewares."""
        app = FastAPI()
        
        register_middlewares(app)
        
        # Check that middlewares were added
        middleware_classes = [m.cls for m in app.user_middleware]
        assert SecurityHeadersMiddleware in middleware_classes
        assert ContentTypeValidationMiddleware in middleware_classes
