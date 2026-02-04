"""
Database configuration and session management.
Uses SQLAlchemy 2.0 async-compatible patterns.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.config.settings import DATABASE_URL

import os


def _calculate_pool_size() -> int:
    """
    DEFECTO-05 FIX: Calculate optimal pool size based on CPU cores.
    Formula: (2 * CPU cores) + 1, capped at 20 for reasonable limits.
    """
    cores = os.cpu_count() or 4
    return min(cores * 2 + 1, 20)


# Create engine with connection pooling and timeouts
# BACK-HIGH-01: Added timeout and pool settings for production reliability
# DEFECTO-05 FIX: Dynamic pool size based on CPU cores
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=_calculate_pool_size(),
    max_overflow=15,  # DEFECTO-05 FIX: Increased for high-load scenarios
    pool_timeout=30,  # Wait max 30s for connection from pool
    pool_recycle=1800,  # Recycle connections after 30 minutes
    connect_args={"connect_timeout": 10},  # Connection establishment timeout
    echo=False,  # Set to True for SQL logging in development
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()

    The session is automatically closed after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions outside of FastAPI.

    Usage:
        with get_db_context() as db:
            db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def safe_commit(db: Session) -> None:
    """
    HIGH-01 FIX: Safe commit with automatic rollback on failure.

    Usage:
        from shared.db import safe_commit
        safe_commit(db)

    Raises the original exception after rolling back.
    """
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
