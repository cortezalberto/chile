"""
Common utilities shared across routers.

NOTE: Admin schemas have been moved to shared/utils/admin_schemas.py
for Clean Architecture compliance (services should not import from routers).
"""

from .base import get_user_id, get_user_email
from .pagination import (
    Pagination,
    PaginatedResponse,
    get_pagination,
    get_pagination_large,
    get_pagination_small,
)

__all__ = [
    # Base utilities
    "get_user_id",
    "get_user_email",
    # Pagination (HIGH-02 FIX)
    "Pagination",
    "PaginatedResponse",
    "get_pagination",
    "get_pagination_large",
    "get_pagination_small",
]
