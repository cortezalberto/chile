"""
Prometheus Metrics Module.

OBS-01: Export application metrics to Prometheus format.
Provides counters, histograms, and gauges for monitoring.
"""

from typing import TYPE_CHECKING
from contextlib import contextmanager
import time

from shared.config.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


# ============================================================================
# Metrics Registry
# ============================================================================

class MetricsRegistry:
    """
    Thread-safe metrics registry using Redis for distributed metrics.
    
    Supports:
    - Counters: Monotonically increasing values
    - Gauges: Values that can go up and down
    - Histograms: Distribution of values with buckets
    """
    
    # Histogram buckets for request durations (in seconds)
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    
    def __init__(self, redis: "Redis", namespace: str = "integrador"):
        self._redis = redis
        self._namespace = namespace
    
    def _key(self, metric_type: str, name: str, labels: dict | None = None) -> str:
        """Generate Redis key for a metric."""
        label_str = ""
        if labels:
            label_str = ":" + ":".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"metrics:{self._namespace}:{metric_type}:{name}{label_str}"
    
    # -------------------------------------------------------------------------
    # Counter Operations
    # -------------------------------------------------------------------------
    
    async def counter_inc(
        self,
        name: str,
        value: int = 1,
        labels: dict | None = None,
    ) -> None:
        """Increment a counter by value."""
        key = self._key("counter", name, labels)
        await self._redis.incrbyfloat(key, value)
    
    async def counter_get(self, name: str, labels: dict | None = None) -> float:
        """Get current counter value."""
        key = self._key("counter", name, labels)
        value = await self._redis.get(key)
        return float(value) if value else 0.0
    
    # -------------------------------------------------------------------------
    # Gauge Operations
    # -------------------------------------------------------------------------
    
    async def gauge_set(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        """Set a gauge to a specific value."""
        key = self._key("gauge", name, labels)
        await self._redis.set(key, str(value))
    
    async def gauge_inc(
        self,
        name: str,
        value: float = 1.0,
        labels: dict | None = None,
    ) -> None:
        """Increment a gauge by value."""
        key = self._key("gauge", name, labels)
        await self._redis.incrbyfloat(key, value)
    
    async def gauge_dec(
        self,
        name: str,
        value: float = 1.0,
        labels: dict | None = None,
    ) -> None:
        """Decrement a gauge by value."""
        await self.gauge_inc(name, -value, labels)
    
    async def gauge_get(self, name: str, labels: dict | None = None) -> float:
        """Get current gauge value."""
        key = self._key("gauge", name, labels)
        value = await self._redis.get(key)
        return float(value) if value else 0.0
    
    # -------------------------------------------------------------------------
    # Histogram Operations
    # -------------------------------------------------------------------------
    
    async def histogram_observe(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
        buckets: tuple = DEFAULT_BUCKETS,
    ) -> None:
        """Observe a value for a histogram."""
        # Increment bucket counters
        for bucket in buckets:
            if value <= bucket:
                bucket_labels = {**(labels or {}), "le": str(bucket)}
                await self.counter_inc(f"{name}_bucket", 1, bucket_labels)
        
        # Increment +Inf bucket
        inf_labels = {**(labels or {}), "le": "+Inf"}
        await self.counter_inc(f"{name}_bucket", 1, inf_labels)
        
        # Track sum and count
        await self.counter_inc(f"{name}_sum", value, labels)
        await self.counter_inc(f"{name}_count", 1, labels)
    
    @contextmanager
    def histogram_timer(
        self,
        name: str,
        labels: dict | None = None,
    ):
        """Context manager to time and observe a duration."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            # Note: This is sync, need to call observe separately
            self._pending_observations.append((name, duration, labels))
    
    # -------------------------------------------------------------------------
    # Export to Prometheus Format
    # -------------------------------------------------------------------------
    
    async def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines = []
        
        # Scan all metric keys
        pattern = f"metrics:{self._namespace}:*"
        cursor = 0
        all_keys = []
        
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            all_keys.extend(keys)
            if cursor == 0:
                break
        
        # Group by metric name
        metrics = {}
        for key in all_keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) >= 4:
                metric_type = parts[2]
                metric_name = parts[3].split(":")[0]  # Remove labels
                
                if metric_name not in metrics:
                    metrics[metric_name] = {"type": metric_type, "values": []}
                
                value = await self._redis.get(key)
                if value:
                    # Parse labels from key
                    labels = {}
                    if len(parts) > 4 or "=" in parts[-1]:
                        label_str = key_str.split(":", 4)[-1] if len(parts) > 4 else ""
                        for pair in label_str.split(":"):
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                labels[k] = v
                    
                    metrics[metric_name]["values"].append({
                        "labels": labels,
                        "value": float(value),
                    })
        
        # Format output
        for name, data in sorted(metrics.items()):
            full_name = f"{self._namespace}_{name}"
            
            # TYPE declaration
            prom_type = "counter" if data["type"] == "counter" else "gauge"
            lines.append(f"# TYPE {full_name} {prom_type}")
            
            # Values
            for entry in data["values"]:
                if entry["labels"]:
                    label_str = ",".join(f'{k}="{v}"' for k, v in entry["labels"].items())
                    lines.append(f"{full_name}{{{label_str}}} {entry['value']}")
                else:
                    lines.append(f"{full_name} {entry['value']}")
        
        return "\n".join(lines)


# ============================================================================
# Pre-defined Application Metrics
# ============================================================================

class AppMetrics:
    """
    Pre-defined application metrics for the Integrador system.
    
    Usage:
        from shared.infrastructure.metrics import get_app_metrics
        
        metrics = await get_app_metrics()
        await metrics.http_request_total("POST", "/api/orders", 201)
        await metrics.websocket_connections_set(150)
    """
    
    def __init__(self, registry: MetricsRegistry):
        self._registry = registry
    
    # -------------------------------------------------------------------------
    # HTTP Metrics
    # -------------------------------------------------------------------------
    
    async def http_request_total(
        self,
        method: str,
        path: str,
        status_code: int,
    ) -> None:
        """Increment HTTP request counter."""
        await self._registry.counter_inc(
            "http_requests_total",
            labels={"method": method, "path": path, "status": str(status_code)},
        )
    
    async def http_request_duration(
        self,
        method: str,
        path: str,
        duration_seconds: float,
    ) -> None:
        """Observe HTTP request duration."""
        await self._registry.histogram_observe(
            "http_request_duration_seconds",
            duration_seconds,
            labels={"method": method, "path": path},
        )
    
    # -------------------------------------------------------------------------
    # WebSocket Metrics
    # -------------------------------------------------------------------------
    
    async def websocket_connections_set(self, count: int) -> None:
        """Set current WebSocket connection count."""
        await self._registry.gauge_set("websocket_connections", count)
    
    async def websocket_messages_total(self, direction: str, event_type: str) -> None:
        """Increment WebSocket message counter."""
        await self._registry.counter_inc(
            "websocket_messages_total",
            labels={"direction": direction, "event": event_type},
        )
    
    # -------------------------------------------------------------------------
    # Database Metrics
    # -------------------------------------------------------------------------
    
    async def db_query_duration(self, operation: str, duration_seconds: float) -> None:
        """Observe database query duration."""
        await self._registry.histogram_observe(
            "db_query_duration_seconds",
            duration_seconds,
            labels={"operation": operation},
        )
    
    async def db_pool_connections(self, active: int, idle: int) -> None:
        """Set database pool connection counts."""
        await self._registry.gauge_set("db_pool_active", active)
        await self._registry.gauge_set("db_pool_idle", idle)
    
    # -------------------------------------------------------------------------
    # Cache Metrics
    # -------------------------------------------------------------------------
    
    async def cache_hit(self, cache_name: str) -> None:
        """Increment cache hit counter."""
        await self._registry.counter_inc(
            "cache_hits_total",
            labels={"cache": cache_name},
        )
    
    async def cache_miss(self, cache_name: str) -> None:
        """Increment cache miss counter."""
        await self._registry.counter_inc(
            "cache_misses_total",
            labels={"cache": cache_name},
        )
    
    # -------------------------------------------------------------------------
    # Business Metrics
    # -------------------------------------------------------------------------
    
    async def orders_total(self, status: str, branch_id: int) -> None:
        """Increment orders counter."""
        await self._registry.counter_inc(
            "orders_total",
            labels={"status": status, "branch_id": str(branch_id)},
        )
    
    async def payments_total(self, provider: str, status: str, amount_cents: int) -> None:
        """Increment payments counter with amount."""
        await self._registry.counter_inc(
            "payments_total",
            labels={"provider": provider, "status": status},
        )
        await self._registry.counter_inc(
            "payments_amount_cents_total",
            amount_cents,
            labels={"provider": provider, "status": status},
        )
    
    async def service_calls_total(self, call_type: str, branch_id: int) -> None:
        """Increment service calls counter."""
        await self._registry.counter_inc(
            "service_calls_total",
            labels={"type": call_type, "branch_id": str(branch_id)},
        )


# ============================================================================
# Global Instance
# ============================================================================

_metrics_registry: MetricsRegistry | None = None
_app_metrics: AppMetrics | None = None


async def init_metrics(redis: "Redis") -> AppMetrics:
    """Initialize the metrics system."""
    global _metrics_registry, _app_metrics
    
    _metrics_registry = MetricsRegistry(redis)
    _app_metrics = AppMetrics(_metrics_registry)
    
    logger.info("Metrics system initialized")
    return _app_metrics


async def get_app_metrics() -> AppMetrics | None:
    """Get the global AppMetrics instance."""
    return _app_metrics


async def get_metrics_registry() -> MetricsRegistry | None:
    """Get the global MetricsRegistry instance."""
    return _metrics_registry


async def export_metrics() -> str:
    """Export all metrics in Prometheus format."""
    if _metrics_registry:
        return await _metrics_registry.export_prometheus()
    return ""
