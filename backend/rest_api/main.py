"""
REST API main application.
Entry point for the FastAPI REST server.

This module creates and configures the FastAPI application.
Configuration is delegated to specialized modules in rest_api/core/.
"""

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from rest_api.core.lifespan import lifespan
from rest_api.core.cors import configure_cors
from rest_api.core.middlewares import register_middlewares
from shared.config.settings import settings
from shared.security.rate_limit import limiter, rate_limit_exceeded_handler

# Import routers (canonical paths - Clean Architecture)
from rest_api.routers.auth import router as auth_router
from rest_api.routers.public.catalog import router as catalog_router
from rest_api.routers.public.health import router as health_router
from rest_api.routers.tables import router as tables_router
from rest_api.routers.diner import router as diner_router
from rest_api.routers.diner.customer import router as customer_router
from rest_api.routers.diner.cart import router as cart_router
from rest_api.routers.kitchen import router as kitchen_router
from rest_api.routers.kitchen.tickets import router as kitchen_tickets_router
from rest_api.routers.billing import router as billing_router
from rest_api.routers.admin import router as admin_router
from rest_api.routers.waiter import router as waiter_router
from rest_api.routers.content.rag import router as rag_router
from rest_api.routers.content.promotions import router as promotions_router
from rest_api.routers.content.recipes import router as recipes_router
from rest_api.routers.content.ingredients import router as ingredients_router
from rest_api.routers.content.catalogs import router as catalogs_router


# =============================================================================
# Create FastAPI Application
# =============================================================================

app = FastAPI(
    title="Integrador REST API",
    description="Restaurant management system API",
    version="0.1.0",
    lifespan=lifespan,
)

# =============================================================================
# Configure Middlewares
# =============================================================================

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Security middlewares (headers, content-type validation)
# NOTE: Register BEFORE CORS - middlewares execute in reverse order
register_middlewares(app)

# CORS configuration - MUST be registered LAST to execute FIRST
# This ensures preflight OPTIONS requests are handled before other middlewares
configure_cors(app)

# =============================================================================
# Register Routers
# =============================================================================

_routers = [
    health_router,
    auth_router,
    catalog_router,
    tables_router,
    diner_router,
    kitchen_router,
    billing_router,
    admin_router,
    rag_router,
    waiter_router,
    promotions_router,
    recipes_router,
    ingredients_router,
    catalogs_router,
    kitchen_tickets_router,
    customer_router,
    cart_router,
]

for router in _routers:
    app.include_router(router)


# =============================================================================
# Development Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "rest_api.main:app",
        host="0.0.0.0",
        port=settings.rest_api_port,
        reload=True,
    )
