"""
OpenTelemetry Instrumentation.

OBS-01: Distributed tracing for the application.
Provides automatic instrumentation for FastAPI, SQLAlchemy, and Redis.
"""

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from shared.config.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


def setup_telemetry(app: "FastAPI") -> None:
    """
    Initialize OpenTelemetry instrumentation.
    
    OBS-01: Sets up distributed tracing with automatic instrumentation
    for FastAPI, SQLAlchemy, and Redis.
    
    Only initializes in production/staging environments unless forced.
    """
    from shared.config.settings import settings
    
    # Check if telemetry should be enabled
    telemetry_enabled = os.getenv("OTEL_ENABLED", "false").lower() == "true"
    if settings.environment == "development" and not telemetry_enabled:
        logger.info("Telemetry disabled in development (set OTEL_ENABLED=true to enable)")
        return
    
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        
    except ImportError:
        logger.warning(
            "OpenTelemetry packages not installed. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy "
            "opentelemetry-instrumentation-redis opentelemetry-exporter-otlp"
        )
        return
    
    # Create resource with service info
    resource = Resource.create({
        SERVICE_NAME: "integrador-api",
        "service.version": "2.0.0",
        "deployment.environment": settings.environment,
    })
    
    # Create tracer provider
    provider = TracerProvider(resource=resource)
    
    # Configure exporter (OTLP to Jaeger/Tempo/etc)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=True,  # Set to False in production with TLS
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(f"OTLP exporter configured: {otlp_endpoint}")
        
    except ImportError:
        logger.warning("OTLP exporter not installed, traces will not be exported")
    except Exception as e:
        logger.warning(f"Failed to configure OTLP exporter: {e}")
    
    # Set as global tracer provider
    trace.set_tracer_provider(provider)
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics,docs,openapi.json,redoc",
    )
    logger.info("FastAPI instrumented")
    
    # Instrument SQLAlchemy
    try:
        from shared.infrastructure.db import engine
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("SQLAlchemy instrumented")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")
    
    # Instrument Redis
    try:
        RedisInstrumentor().instrument()
        logger.info("Redis instrumented")
    except Exception as e:
        logger.warning(f"Failed to instrument Redis: {e}")
    
    # Instrument logging (adds trace context to logs)
    try:
        LoggingInstrumentor().instrument(set_logging_format=False)
        logger.info("Logging instrumented with trace context")
    except Exception as e:
        logger.warning(f"Failed to instrument logging: {e}")
    
    logger.info("Telemetry setup complete")


def get_tracer(name: str = __name__):
    """Get a tracer for manual instrumentation."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None


def get_current_trace_id() -> str | None:
    """Get current trace ID for correlation."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            context = span.get_span_context()
            if context.is_valid:
                return format(context.trace_id, '032x')
    except ImportError:
        pass
    return None
