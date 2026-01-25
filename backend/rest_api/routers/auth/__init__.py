"""
Authentication routers - /api/auth/*
Handles login, logout, token refresh, and user info.
"""

from .routes import router

__all__ = ["router"]
