"""
Metrics endpoint for Prometheus scraping.

OBS-01: Exposes /metrics endpoint for Prometheus to scrape.

Usage:
    GET /metrics -> Prometheus text format metrics
"""

from fastapi import APIRouter, Response

from shared.infrastructure.metrics import export_metrics

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """
    Expose application metrics in Prometheus text format.
    
    This endpoint should be scraped by Prometheus at regular intervals.
    It is excluded from OpenAPI schema for security.
    """
    content = await export_metrics()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
