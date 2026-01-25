"""
Billing routers - /api/billing/*
Handles payment processing, checks, and Mercado Pago integration.
"""

from .routes import router

__all__ = ["router"]
