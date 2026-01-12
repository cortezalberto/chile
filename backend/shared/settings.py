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
