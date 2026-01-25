"""
Prometheus Metrics Export for WebSocket Gateway.

Formats internal metrics in Prometheus exposition format.
No external dependencies required.

ARCH-OPP-07 FIX: Added Prometheus-compatible metrics endpoint.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ws_gateway.connection_manager import ConnectionManager


# =============================================================================
# Metric Types
# =============================================================================


class MetricType(str, Enum):
    """Prometheus metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricDefinition:
    """Definition of a metric for Prometheus output."""

    name: str
    help_text: str
    metric_type: MetricType
    labels: list[str] | None = None


# =============================================================================
# Metric Definitions
# =============================================================================

# WebSocket Connection Metrics
METRIC_DEFINITIONS: list[MetricDefinition] = [
    # Connection gauges
    MetricDefinition(
        name="wsgateway_connections_total",
        help_text="Current number of active WebSocket connections",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_connections_max",
        help_text="Maximum allowed WebSocket connections",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_connections_utilization_percent",
        help_text="Connection utilization percentage",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_users_connected",
        help_text="Number of unique users connected",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_branches_with_connections",
        help_text="Number of branches with active connections",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_sectors_with_connections",
        help_text="Number of sectors with active connections",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_sessions_with_connections",
        help_text="Number of table sessions with active connections",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_admin_connections",
        help_text="Number of admin/manager connections",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_dead_connections_pending",
        help_text="Number of dead connections pending cleanup",
        metric_type=MetricType.GAUGE,
    ),

    # Broadcast counters
    MetricDefinition(
        name="wsgateway_broadcasts_total",
        help_text="Total number of broadcast operations",
        metric_type=MetricType.COUNTER,
    ),
    MetricDefinition(
        name="wsgateway_broadcasts_failed",
        help_text="Number of failed broadcast operations",
        metric_type=MetricType.COUNTER,
    ),
    MetricDefinition(
        name="wsgateway_broadcasts_failed_recipients",
        help_text="Total failed recipients across all broadcasts",
        metric_type=MetricType.COUNTER,
    ),
    MetricDefinition(
        name="wsgateway_broadcasts_rate_limited",
        help_text="Number of broadcasts dropped due to rate limiting",
        metric_type=MetricType.COUNTER,
    ),

    # Connection rejection counters
    MetricDefinition(
        name="wsgateway_connections_rejected_total",
        help_text="Total rejected connections",
        metric_type=MetricType.COUNTER,
        labels=["reason"],
    ),

    # Event counters
    MetricDefinition(
        name="wsgateway_events_processed",
        help_text="Total events processed from Redis",
        metric_type=MetricType.COUNTER,
    ),
    MetricDefinition(
        name="wsgateway_events_dropped",
        help_text="Events dropped due to queue overflow",
        metric_type=MetricType.COUNTER,
    ),
    MetricDefinition(
        name="wsgateway_events_invalid_schema",
        help_text="Events rejected due to invalid schema",
        metric_type=MetricType.COUNTER,
    ),

    # Lock metrics
    MetricDefinition(
        name="wsgateway_locks_cleaned",
        help_text="Total locks cleaned up",
        metric_type=MetricType.COUNTER,
    ),
    MetricDefinition(
        name="wsgateway_branch_locks",
        help_text="Current number of branch locks",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_user_locks",
        help_text="Current number of user locks",
        metric_type=MetricType.GAUGE,
    ),

    # Rate limiter metrics
    MetricDefinition(
        name="wsgateway_rate_limiter_tracked",
        help_text="Connections tracked by rate limiter",
        metric_type=MetricType.GAUGE,
    ),

    # Heartbeat metrics
    MetricDefinition(
        name="wsgateway_heartbeat_tracked_connections",
        help_text="Connections tracked by heartbeat tracker",
        metric_type=MetricType.GAUGE,
    ),
    MetricDefinition(
        name="wsgateway_heartbeat_timeout_seconds",
        help_text="Heartbeat timeout in seconds",
        metric_type=MetricType.GAUGE,
    ),
]


# =============================================================================
# Prometheus Formatter
# =============================================================================


class PrometheusFormatter:
    """
    Formats metrics in Prometheus text exposition format.

    Reference: https://prometheus.io/docs/instrumenting/exposition_formats/

    Usage:
        formatter = PrometheusFormatter()
        output = formatter.format_metrics(stats)
    """

    def __init__(self, prefix: str = "wsgateway"):
        """
        Initialize formatter.

        Args:
            prefix: Prefix for all metric names.
        """
        self._prefix = prefix

    def format_metric(
        self,
        name: str,
        value: float | int,
        help_text: str,
        metric_type: MetricType,
        labels: dict[str, str] | None = None,
    ) -> str:
        """
        Format a single metric in Prometheus format.

        Args:
            name: Metric name.
            value: Metric value.
            help_text: Help text description.
            metric_type: Prometheus metric type.
            labels: Optional label key-value pairs.

        Returns:
            Prometheus-formatted metric string.
        """
        lines = []

        # HELP line
        lines.append(f"# HELP {name} {help_text}")

        # TYPE line
        lines.append(f"# TYPE {name} {metric_type.value}")

        # Value line with optional labels
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")

        return "\n".join(lines)

    def format_all_metrics(self, stats: dict[str, Any]) -> str:
        """
        Format all metrics from ConnectionManager stats.

        Args:
            stats: Stats dictionary from ConnectionManager.get_stats().

        Returns:
            Complete Prometheus exposition format string.
        """
        lines: list[str] = []
        metrics = stats.get("metrics", {})
        heartbeat_stats = stats.get("heartbeat_stats", {})

        # Connection gauges
        lines.append(self.format_metric(
            "wsgateway_connections_total",
            stats.get("total_connections", 0),
            "Current number of active WebSocket connections",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_connections_max",
            stats.get("max_connections", 1000),
            "Maximum allowed WebSocket connections",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_connections_utilization_percent",
            stats.get("utilization_percent", 0),
            "Connection utilization percentage",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_users_connected",
            stats.get("users_connected", 0),
            "Number of unique users connected",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_branches_with_connections",
            stats.get("branches_with_connections", 0),
            "Number of branches with active connections",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_sectors_with_connections",
            stats.get("sectors_with_connections", 0),
            "Number of sectors with active connections",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_sessions_with_connections",
            stats.get("sessions_with_connections", 0),
            "Number of table sessions with active connections",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_admin_connections",
            stats.get("admin_connections", 0),
            "Number of admin/manager connections",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_dead_connections_pending",
            stats.get("dead_connections_pending", 0),
            "Dead connections pending cleanup",
            MetricType.GAUGE,
        ))

        # Broadcast counters from metrics
        lines.append(self.format_metric(
            "wsgateway_broadcasts_total",
            metrics.get("broadcasts_total", 0),
            "Total broadcast operations",
            MetricType.COUNTER,
        ))

        lines.append(self.format_metric(
            "wsgateway_broadcasts_failed",
            metrics.get("broadcasts_failed", 0),
            "Failed broadcast operations",
            MetricType.COUNTER,
        ))

        lines.append(self.format_metric(
            "wsgateway_broadcasts_failed_recipients",
            metrics.get("broadcasts_failed_recipients", 0),
            "Total failed recipients",
            MetricType.COUNTER,
        ))

        lines.append(self.format_metric(
            "wsgateway_broadcasts_rate_limited",
            metrics.get("broadcasts_rate_limited", 0),
            "Rate-limited broadcasts",
            MetricType.COUNTER,
        ))

        # Connection rejection counters with labels
        lines.append("# HELP wsgateway_connections_rejected_total Rejected connections by reason")
        lines.append("# TYPE wsgateway_connections_rejected_total counter")
        lines.append(f'wsgateway_connections_rejected_total{{reason="limit"}} {metrics.get("connections_rejected_limit", 0)}')
        lines.append(f'wsgateway_connections_rejected_total{{reason="rate_limit"}} {metrics.get("connections_rejected_rate_limit", 0)}')
        lines.append(f'wsgateway_connections_rejected_total{{reason="auth"}} {metrics.get("connections_rejected_auth", 0)}')

        # Event counters
        lines.append(self.format_metric(
            "wsgateway_events_processed",
            metrics.get("events_processed", 0),
            "Events processed from Redis",
            MetricType.COUNTER,
        ))

        lines.append(self.format_metric(
            "wsgateway_events_dropped",
            metrics.get("events_dropped", 0),
            "Events dropped due to queue overflow",
            MetricType.COUNTER,
        ))

        lines.append(self.format_metric(
            "wsgateway_events_invalid_schema",
            metrics.get("events_invalid_schema", 0),
            "Events with invalid schema",
            MetricType.COUNTER,
        ))

        # Lock metrics
        lines.append(self.format_metric(
            "wsgateway_locks_cleaned",
            metrics.get("locks_cleaned", 0),
            "Total locks cleaned up",
            MetricType.COUNTER,
        ))

        lines.append(self.format_metric(
            "wsgateway_branch_locks",
            stats.get("branch_locks_count", 0),
            "Current branch locks",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_user_locks",
            stats.get("user_locks_count", 0),
            "Current user locks",
            MetricType.GAUGE,
        ))

        # Rate limiter
        lines.append(self.format_metric(
            "wsgateway_rate_limiter_tracked",
            stats.get("rate_limiter_tracked", 0),
            "Connections tracked by rate limiter",
            MetricType.GAUGE,
        ))

        # Heartbeat metrics
        lines.append(self.format_metric(
            "wsgateway_heartbeat_tracked_connections",
            heartbeat_stats.get("tracked_connections", 0),
            "Connections tracked by heartbeat",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_heartbeat_timeout_seconds",
            heartbeat_stats.get("timeout_seconds", 60),
            "Heartbeat timeout",
            MetricType.GAUGE,
        ))

        lines.append(self.format_metric(
            "wsgateway_heartbeat_oldest_age_seconds",
            heartbeat_stats.get("oldest_heartbeat_age", 0),
            "Oldest heartbeat age in seconds",
            MetricType.GAUGE,
        ))

        # Timestamp
        lines.append(self.format_metric(
            "wsgateway_scrape_timestamp",
            int(time.time()),
            "Timestamp of metrics scrape",
            MetricType.GAUGE,
        ))

        return "\n".join(lines) + "\n"


# =============================================================================
# Singleton formatter
# =============================================================================

_formatter: PrometheusFormatter | None = None


def get_prometheus_formatter() -> PrometheusFormatter:
    """Get singleton Prometheus formatter."""
    global _formatter
    if _formatter is None:
        _formatter = PrometheusFormatter()
    return _formatter


async def generate_prometheus_metrics(manager: "ConnectionManager") -> str:
    """
    Generate Prometheus metrics from ConnectionManager.

    Args:
        manager: ConnectionManager instance.

    Returns:
        Prometheus exposition format string.
    """
    stats = await manager.get_stats()
    formatter = get_prometheus_formatter()
    return formatter.format_all_metrics(stats)
