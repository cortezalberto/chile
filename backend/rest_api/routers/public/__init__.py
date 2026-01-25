"""
Public routers - No authentication required.
- /api/public/* - Public menu endpoints
- /api/health - Health check
"""

from .catalog import router as catalog_router
from .health import router as health_router

__all__ = ["catalog_router", "health_router"]
