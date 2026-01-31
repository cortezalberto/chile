"""
Application settings loaded from environment variables.
Uses pydantic-settings for type-safe configuration.
"""

from functools import lru_cache
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with defaults for development."""

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/menu_ops"

    # Redis
    # Default matches docker-compose.yml which exposes Redis on 6380
    redis_url: str = "redis://localhost:6380"

    # JWT Configuration
    jwt_secret: str = "dev-secret-change-me-in-production"
    jwt_issuer: str = "menu-ops"
    jwt_audience: str = "menu-ops-users"
    # SEC-01: Short-lived access tokens (15 min) reduce window of exposure if token is compromised
    # Refresh tokens (7 days) allow seamless re-authentication without user intervention
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # SEC-09: HttpOnly Cookie settings for refresh token
    # secure=True requires HTTPS (automatically False in development)
    # samesite="lax" allows cookies on top-level navigation (good balance of security/usability)
    cookie_secure: bool = False  # Set to True in production (.env)
    cookie_samesite: str = "lax"  # "lax" or "strict"
    cookie_domain: str = ""  # Empty = current domain only, set for cross-subdomain

    # Table Token (HMAC for diner authentication)
    table_token_secret: str = "table-token-secret-change-me"
    # CRIT-04 FIX: Reduced from 8h to 3h to limit token exposure window
    jwt_table_token_expire_hours: int = 3

    # CRIT-03 FIX: CORS configuration for production
    # Comma-separated list of allowed origins (empty uses default localhost list)
    allowed_origins: str = ""

    # Ollama (RAG)
    ollama_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    chat_model: str = "qwen2.5:7b"

    # Mercado Pago
    mercadopago_access_token: str = ""
    mercadopago_webhook_secret: str = ""
    mercadopago_notification_url: str = ""

    # Server ports
    rest_api_port: int = 8000
    ws_gateway_port: int = 8001

    # Base URL for payment redirects
    base_url: str = "http://localhost:5176"

    # Environment
    environment: str = "development"
    debug: bool = True

    # Rate limiting - SHARED-LOW-01 FIX: Moved from hardcoded values
    login_rate_limit: int = 5  # Max login attempts per window
    login_rate_window: int = 60  # Window in seconds

    # WebSocket - WS-MED-02 FIX: Moved from hardcoded values
    # LOAD-LEVEL1: Reduced per-user limit to control total connections
    ws_max_connections_per_user: int = 3  # Was 5, reduced to limit total connections
    ws_heartbeat_timeout: int = 60  # Consider connection dead after this many seconds
    ws_max_message_size: int = 64 * 1024  # 64 KB
    # LOAD-LEVEL2: Global connection limit to prevent resource exhaustion
    ws_max_total_connections: int = 1000  # Maximum total WebSocket connections
    # LOAD-LEVEL2: Rate limiting for WebSocket messages
    ws_message_rate_limit: int = 20  # Max messages per window per connection
    ws_message_rate_window: int = 1  # Window in seconds
    # LOAD-LEVEL2: Broadcast optimization
    ws_broadcast_batch_size: int = 50  # Connections to send to in parallel
    # HIGH-WS-01 FIX: Configurable callback timeout for event processing
    ws_event_callback_timeout: int = 5  # Timeout in seconds for event callbacks

    # Redis - REDIS-MED-03 FIX: Moved from hardcoded values
    # LOAD-LEVEL1: Increased pool sizes for 400+ users
    redis_pool_max_connections: int = 50  # Was 20, increased for higher concurrency
    redis_sync_pool_max_connections: int = 20  # New: Pool for sync operations
    redis_socket_timeout: int = 5  # Socket timeout in seconds (for both connect and read/write)
    # MED-WS-03 FIX: Reduced from 100 to 20 - with exponential backoff, this is ~10 min of retries
    redis_max_reconnect_attempts: int = 20  # Max reconnection attempts for subscriber
    # LOAD-LEVEL1: Increased queue and batch sizes
    redis_event_queue_size: int = 5000  # Was 1000, increased for burst handling
    redis_event_batch_size: int = 50  # Was 10, increased for faster processing
    redis_publish_max_retries: int = 3  # Max retries for event publishing
    redis_publish_retry_delay: float = 0.1  # Delay between retries in seconds
    # HIGH-05 FIX: Configurable timeouts for pubsub operations
    redis_pubsub_cleanup_timeout: float = 5.0  # Timeout for pubsub cleanup operations (unsubscribe/close)
    redis_pubsub_reconnect_total_timeout: float = 15.0  # Total timeout for reconnection attempts
    # MED-01 FIX: Event processing order configuration
    redis_event_strict_ordering: bool = False  # If True, retried events go to front of queue (strict FIFO)
    redis_event_staleness_threshold: float = 5.0  # Warn if event waited > N seconds in queue

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def validate_production_secrets(self) -> list[str]:
        """
        SHARED-CRIT-03 FIX: Validate that secrets are properly configured for production.
        Returns a list of validation errors. Empty list means all checks pass.
        """
        errors = []

        # Define weak/default secrets that MUST be changed in production
        WEAK_SECRETS = {
            "dev-secret-change-me-in-production",
            "table-token-secret-change-me",
            "secret",
            "password",
            "changeme",
            "default",
        }

        if self.environment == "production":
            # Check JWT secret
            if self.jwt_secret in WEAK_SECRETS or len(self.jwt_secret) < 32:
                errors.append(
                    "JWT_SECRET must be at least 32 characters and not a default value in production"
                )

            # Check table token secret
            if self.table_token_secret in WEAK_SECRETS or len(self.table_token_secret) < 32:
                errors.append(
                    "TABLE_TOKEN_SECRET must be at least 32 characters and not a default value in production"
                )

            # Check debug is disabled
            if self.debug:
                errors.append("DEBUG must be False in production")

            # Check Mercado Pago if using payments
            if self.mercadopago_access_token and not self.mercadopago_webhook_secret:
                errors.append(
                    "MERCADOPAGO_WEBHOOK_SECRET must be set when using Mercado Pago"
                )

            # CRIT-03 FIX: Check CORS is configured for production
            if not self.allowed_origins:
                errors.append(
                    "ALLOWED_ORIGINS must be set in production (comma-separated list of allowed domains)"
                )

        return errors


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience exports
settings = get_settings()

# Direct access to commonly used settings
DATABASE_URL = settings.database_url
REDIS_URL = settings.redis_url
JWT_SECRET = settings.jwt_secret
JWT_ISSUER = settings.jwt_issuer
JWT_AUDIENCE = settings.jwt_audience
TABLE_TOKEN_SECRET = settings.table_token_secret
OLLAMA_URL = settings.ollama_url
EMBED_MODEL = settings.embed_model
CHAT_MODEL = settings.chat_model
