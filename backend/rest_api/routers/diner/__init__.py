"""
Diner routers - /api/diner/*, /api/customer/*
Handles diner operations and customer loyalty features.
"""

from .orders import router as diner_router
from .customer import router as customer_router

# Backward compatibility: export 'router' for old import paths
router = diner_router

__all__ = ["router", "diner_router", "customer_router"]
