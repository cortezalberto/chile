"""
Payment Services - Payment processing and external integrations.

Provides:
- FIFO payment allocation for split payments
- Mercado Pago webhook handling with retry queue
- Circuit breaker for external API resilience
"""

from .allocation import (
    create_charges_for_check,
    allocate_payment_fifo,
    get_diner_balance,
    get_all_diner_balances,
)
from .webhook_retry import (
    WebhookRetryQueue,
    WebhookRetryItem,
    webhook_retry_queue,
    start_retry_processor,
)
from .mp_webhook import (
    handle_mp_webhook_retry,
    register_mp_webhook_handler,
)
from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerStats,
    CircuitBreakerError,
    CircuitState,
    mercadopago_breaker,
    get_all_breaker_stats,
)

__all__ = [
    # Allocation
    "create_charges_for_check",
    "allocate_payment_fifo",
    "get_diner_balance",
    "get_all_diner_balances",
    # Webhook retry
    "WebhookRetryQueue",
    "WebhookRetryItem",
    "webhook_retry_queue",
    "start_retry_processor",
    # MP webhook
    "handle_mp_webhook_retry",
    "register_mp_webhook_handler",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerStats",
    "CircuitBreakerError",
    "CircuitState",
    "mercadopago_breaker",
    "get_all_breaker_stats",
]
