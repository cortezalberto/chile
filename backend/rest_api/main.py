"""
REST API main application.
Entry point for the FastAPI REST server.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from rest_api.db import engine, SessionLocal
from rest_api.models import Base
from rest_api.seed import seed
from rest_api.routers.auth import router as auth_router
from rest_api.routers.catalog import router as catalog_router
from rest_api.routers.tables import router as tables_router
from rest_api.routers.diner import router as diner_router
from rest_api.routers.kitchen import router as kitchen_router
from rest_api.routers.billing import router as billing_router
from rest_api.routers.admin import router as admin_router
from rest_api.routers.rag import router as rag_router
from rest_api.routers.waiter import router as waiter_router
from rest_api.routers.promotions import router as promotions_router
from rest_api.routers.recipes import router as recipes_router
from rest_api.routers.ingredients import router as ingredients_router
from rest_api.routers.catalogs import router as catalogs_router
from rest_api.routers.kitchen_tickets import router as kitchen_tickets_router
from shared.settings import settings
from shared.logging import setup_logging, rest_api_logger as logger
from shared.rate_limit import limiter, rate_limit_exceeded_handler
from shared.events import close_redis_pool
from rest_api.services.webhook_retry import webhook_retry_queue, start_retry_processor
from rest_api.services.circuit_breaker import get_all_breaker_stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Runs on startup and shutdown.
    """
    # Initialize logging
    setup_logging()

    # SHARED-CRIT-03 FIX: Validate production secrets before startup
    secret_errors = settings.validate_production_secrets()
    if secret_errors:
        for error in secret_errors:
            logger.error("Configuration error: %s", error)
        if settings.environment == "production":
            raise RuntimeError(
                f"Production configuration errors: {'; '.join(secret_errors)}. "
                "Server will not start with insecure configuration."
            )
        else:
            logger.warning(
                "Running with insecure defaults (acceptable for development only)"
            )

    # Startup
    logger.info("Starting REST API", port=settings.rest_api_port, env=settings.environment)

    # Enable pgvector extension BEFORE creating tables (required for VECTOR type)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    logger.info("pgvector extension enabled")

    # Create database tables (after pgvector extension is available)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Seed initial data
    with SessionLocal() as db:
        seed(db)

    # REC-02 FIX: Register webhook retry handlers and start processor
    from rest_api.services.mp_webhook_handler import register_mp_webhook_handler
    register_mp_webhook_handler()
    logger.info("Webhook retry handlers registered")

    # Start background retry processor (non-blocking)
    import asyncio
    asyncio.create_task(start_retry_processor(interval_seconds=30.0))
    logger.info("Webhook retry processor started")

    yield

    # Shutdown
    logger.info("Shutting down REST API")

    # BACK-HIGH-04: Close Redis connection pool on shutdown
    await close_redis_pool()
    logger.info("Redis connection pool closed")


# Create FastAPI application
app = FastAPI(
    title="Integrador REST API",
    description="Restaurant management system API",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/api/health")
def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "rest-api",
        "environment": settings.environment,
    }


@app.get("/api/health/detailed")
async def detailed_health_check():
    """
    Detailed health check that verifies connectivity to dependencies.
    Returns status of PostgreSQL and Redis connections.
    """
    from rest_api.db import SessionLocal
    from shared.events import get_redis_pool

    checks = {
        "service": "rest-api",
        "environment": settings.environment,
        "dependencies": {},
    }
    all_healthy = True

    # Check PostgreSQL
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["dependencies"]["postgresql"] = {"status": "healthy"}
    except Exception as e:
        checks["dependencies"]["postgresql"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # Check Redis
    # REDIS-01 FIX: Use pooled connection instead of creating temporary one
    try:
        redis = await get_redis_pool()
        await redis.ping()
        # Note: Don't close pooled connection - pool manages lifecycle
        checks["dependencies"]["redis"] = {"status": "healthy"}
    except Exception as e:
        checks["dependencies"]["redis"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # REC-01/REC-02 FIX: Include circuit breaker and webhook retry stats
    checks["circuit_breakers"] = get_all_breaker_stats()
    checks["webhook_retry"] = await webhook_retry_queue.get_stats()

    checks["status"] = "healthy" if all_healthy else "degraded"

    # Return 503 if any dependency is down
    if not all_healthy:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=checks, status_code=503)

    return checks


# =============================================================================
# Include Routers
# =============================================================================

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(tables_router)
app.include_router(diner_router)
app.include_router(kitchen_router)
app.include_router(billing_router)
app.include_router(admin_router)
app.include_router(rag_router)
app.include_router(waiter_router)
app.include_router(promotions_router)
app.include_router(recipes_router)
app.include_router(ingredients_router)
app.include_router(catalogs_router)
app.include_router(kitchen_tickets_router)


# =============================================================================
# Development entry point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "rest_api.main:app",
        host="0.0.0.0",
        port=settings.rest_api_port,
        reload=True,
    )
