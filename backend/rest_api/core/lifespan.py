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

    # OUTBOX-PATTERN: Start outbox processor for guaranteed event delivery
    from rest_api.services.events.outbox_processor import start_outbox_processor
    await start_outbox_processor()
    logger.info("Outbox processor started")

    # REDIS-02: Warm caches on startup to prevent cold-start latency
    try:
        from shared.infrastructure.events import get_redis_client
        from shared.infrastructure.cache.warmer import (
            warm_caches_on_startup,
            start_refresh_ahead,
        )
        redis = await get_redis_client()
        await warm_caches_on_startup(redis, SessionLocal)
        logger.info("Cache warming completed")
        
        # OPT-03: Start refresh-ahead scheduler for proactive cache refresh
        await start_refresh_ahead(redis, SessionLocal)
        logger.info("Refresh-ahead scheduler started")
        
        # OBS-01: Initialize Prometheus metrics system
        from shared.infrastructure.metrics import init_metrics
        await init_metrics(redis)
        logger.info("Prometheus metrics initialized")
    except Exception as e:
        # Cache warming failure is non-fatal - app can still start
        logger.warning("Cache/metrics initialization failed (non-fatal)", error=str(e))

    yield

    # Shutdown
    logger.info("Shutting down REST API")

    # OPT-03: Stop refresh-ahead scheduler
    try:
        from shared.infrastructure.cache.warmer import stop_refresh_ahead
        await stop_refresh_ahead()
        logger.info("Refresh-ahead scheduler stopped")
    except Exception as e:
        logger.warning("Failed to stop refresh-ahead scheduler", error=str(e))

    # OUTBOX-PATTERN: Stop outbox processor gracefully
    from rest_api.services.events.outbox_processor import stop_outbox_processor
    await stop_outbox_processor()
    logger.info("Outbox processor stopped")

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
