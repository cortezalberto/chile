"""
Request Correlation Middleware.

OBS-02: Adds correlation IDs to all requests for distributed tracing.
"""

import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.config.logging import get_logger

logger = get_logger(__name__)

# Context variable for request ID (thread-safe)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation IDs to all requests.
    
    OBS-02: Enables request tracing across services and logs.
    
    - If X-Request-ID header is present, uses that value
    - Otherwise generates a new UUID
    - Sets the ID in context for logging
    - Returns the ID in response headers
    """
    
    HEADER_NAME = "X-Request-ID"
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Get or generate request ID
        request_id = request.headers.get(self.HEADER_NAME)
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Set in context variable for logging
        token = request_id_var.set(request_id)
        
        try:
            # Add to request state for easy access
            request.state.request_id = request_id
            
            # Process request
            response = await call_next(request)
            
            # Add to response headers
            response.headers[self.HEADER_NAME] = request_id
            
            return response
        finally:
            # Reset context
            request_id_var.reset(token)


class CorrelationIdFilter:
    """
    Logging filter that adds request_id to log records.
    
    Usage:
        import logging
        handler = logging.StreamHandler()
        handler.addFilter(CorrelationIdFilter())
    """
    
    def filter(self, record) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def setup_correlation_logging():
    """
    Configure logging to include correlation IDs.
    
    Adds the CorrelationIdFilter to the root logger.
    """
    import logging
    
    # Add filter to root logger handlers
    root_logger = logging.getLogger()
    correlation_filter = CorrelationIdFilter()
    
    for handler in root_logger.handlers:
        handler.addFilter(correlation_filter)
    
    logger.info("Correlation ID logging configured")
