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
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Table Token (HMAC for diner authentication)
    table_token_secret: str = "table-token-secret-change-me"

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
