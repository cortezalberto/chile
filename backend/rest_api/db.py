"""
Database configuration and session management.
Uses SQLAlchemy 2.0 async-compatible patterns.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.settings import DATABASE_URL


# Create engine with connection pooling and timeouts
# BACK-HIGH-01: Added timeout and pool settings for production reliability
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,
    max_overflow=10,
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
