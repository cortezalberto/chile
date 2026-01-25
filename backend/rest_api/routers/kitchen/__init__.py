"""
Kitchen routers - /api/kitchen/*
Handles kitchen staff operations and ticket management.
"""

from .rounds import router as rounds_router
from .tickets import router as tickets_router

# Backward compatibility: export 'router' for old import paths
router = rounds_router

__all__ = ["router", "rounds_router", "tickets_router"]
