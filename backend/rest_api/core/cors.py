"""
CORS (Cross-Origin Resource Sharing) configuration.
Configures allowed origins, methods, and headers for the API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config.settings import settings


# Default origins for development (localhost ports)
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",  # Vite default
    "http://localhost:5176",  # pwaMenu
    "http://localhost:5177",  # Dashboard
    "http://localhost:5178",  # pwaWaiter
    "http://localhost:5179",  # Dashboard alternate port
    "http://localhost:5180",  # Future use
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5176",
    "http://127.0.0.1:5177",
    "http://127.0.0.1:5178",
    "http://127.0.0.1:5179",
    "http://127.0.0.1:5180",
]

# Allowed HTTP methods
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

# Allowed request headers
ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Table-Token",
    "X-Request-ID",
    "X-Requested-With",  # CSRF protection header from pwaMenu
    "X-Device-Id",  # Customer recognition header
    "Accept",
    "Accept-Language",
    "Cache-Control",
]


def get_cors_origins() -> list[str]:
    """
    Get CORS origins based on environment.

    In production: Uses ALLOWED_ORIGINS from settings (comma-separated).
    In development: Uses DEFAULT_CORS_ORIGINS.
    """
    if settings.allowed_origins:
        return [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    return DEFAULT_CORS_ORIGINS


def configure_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware on the FastAPI application.

    Production: Set ALLOWED_ORIGINS env var (comma-separated).
    Development: Uses default localhost ports automatically.
    """
    # DEV-CORS-FIX: Use short max_age in development to avoid preflight cache issues
    # Production should use longer max_age (600) for performance
    max_age = 0 if settings.environment == "development" else 600

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=["X-Request-ID"],
        max_age=max_age,
    )
