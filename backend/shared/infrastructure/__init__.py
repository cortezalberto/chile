"""
Infrastructure module: Database and Redis/events.

Provides:
- Database sessions and transactions (db.py)
- Redis pub/sub for real-time events (events/)
"""

from shared.infrastructure.db import (
    engine,
    SessionLocal,
    get_db,
    get_db_context,
    safe_commit,
)
from shared.infrastructure.events import (
    get_redis_pool,
    get_redis_sync_client,
    close_redis_pool,
    publish_event,
)

__all__ = [
    # db
    "engine",
    "SessionLocal",
    "get_db",
    "get_db_context",
    "safe_commit",
    # events (Redis)
    "get_redis_pool",
    "get_redis_sync_client",
    "close_redis_pool",
    "publish_event",
]
