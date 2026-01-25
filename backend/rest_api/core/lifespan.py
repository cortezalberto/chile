"""
Application lifespan handler.
Manages startup and shutdown events for the FastAPI application.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from shared.infrastructure.db import engine, SessionLocal
from shared.config.settings import settings
from shared.config.logging import setup_logging, rest_api_logger as logger
from shared.infrastructure.events import close_redis_pool
from rest_api.models import Base
from rest_api.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Runs on startup and shutdown.
    """
    # Initialize logging
    setup_logging()

    # Validate production secrets before startup
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

    # Register webhook retry handlers and start processor
    from rest_api.services.payments.mp_webhook import register_mp_webhook_handler
    register_mp_webhook_handler()
    logger.info("Webhook retry handlers registered")

    # Start background retry processor (non-blocking)
    import asyncio
    from rest_api.services.payments.webhook_retry import start_retry_processor
    asyncio.create_task(start_retry_processor(interval_seconds=30.0))
    logger.info("Webhook retry processor started")

    yield

    # Shutdown
    logger.info("Shutting down REST API")

    # Close Ollama HTTP client on shutdown
    from rest_api.services.rag.service import close_ollama_client
    await close_ollama_client()
    logger.info("Ollama HTTP client closed")

    # SHARED-RATELIMIT-02 FIX: Close rate limit executor on shutdown
    from shared.security.rate_limit import close_rate_limit_executor
    close_rate_limit_executor()

    # Close Redis connection pool on shutdown
    await close_redis_pool()
    logger.info("Redis connection pool closed")
