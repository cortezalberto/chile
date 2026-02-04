"""
Metrics infrastructure module.

OBS-01: Prometheus-compatible metrics for application monitoring.
"""

from shared.infrastructure.metrics.prometheus import (
    MetricsRegistry,
    AppMetrics,
    init_metrics,
    get_app_metrics,
    get_metrics_registry,
    export_metrics,
)

__all__ = [
    "MetricsRegistry",
    "AppMetrics",
    "init_metrics",
    "get_app_metrics",
    "get_metrics_registry",
    "export_metrics",
]
