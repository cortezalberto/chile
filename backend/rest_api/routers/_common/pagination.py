"""
Standardized Pagination for all routers.
HIGH-02 FIX: Provides consistent pagination across all endpoints.

Usage:
    from rest_api.routers._common.pagination import Pagination, get_pagination

    @router.get("/products")
    def list_products(
        pagination: Pagination = Depends(get_pagination),
        db: Session = Depends(get_db),
    ):
        query = query.offset(pagination.offset).limit(pagination.limit)
        return {"items": items, "pagination": pagination.to_dict(total=count)}
"""

from dataclasses import dataclass
from typing import Any
from fastapi import Query

from shared.config.constants import Limits


@dataclass
class Pagination:
    """
    Pagination parameters with validation.

    Attributes:
        limit: Maximum items per page (1 to max_limit)
        offset: Number of items to skip
        max_limit: Maximum allowed limit (default 200)
    """

    limit: int
    offset: int
    max_limit: int = Limits.MAX_PAGE_SIZE

    def __post_init__(self):
        """Validate and normalize values."""
        self.limit = min(max(1, self.limit), self.max_limit)
        self.offset = max(0, self.offset)

    @property
    def page(self) -> int:
        """Calculate current page number (1-indexed)."""
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1

    @property
    def has_next(self) -> bool:
        """Check if there could be more items (requires total)."""
        # This is a hint - actual check needs total count
        return True

    def to_dict(self, total: int | None = None) -> dict[str, Any]:
        """
        Convert to dictionary for response.

        Args:
            total: Total count of items (optional)

        Returns:
            Dictionary with pagination metadata
        """
        result = {
            "limit": self.limit,
            "offset": self.offset,
            "page": self.page,
        }

        if total is not None:
            result["total"] = total
            result["pages"] = (total + self.limit - 1) // self.limit if self.limit > 0 else 1
            result["has_next"] = self.offset + self.limit < total
            result["has_prev"] = self.offset > 0

        return result

    def next_page_offset(self) -> int:
        """Get offset for next page."""
        return self.offset + self.limit

    def prev_page_offset(self) -> int:
        """Get offset for previous page."""
        return max(0, self.offset - self.limit)


def get_pagination(
    limit: int = Query(
        default=Limits.DEFAULT_PAGE_SIZE,
        ge=1,
        le=Limits.MAX_PAGE_SIZE,
        description="Maximum number of items to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip",
    ),
) -> Pagination:
    """
    FastAPI dependency for pagination.

    Usage:
        @router.get("/items")
        def list_items(pagination: Pagination = Depends(get_pagination)):
            ...
    """
    return Pagination(limit=limit, offset=offset)


def get_pagination_large(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of items to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip",
    ),
) -> Pagination:
    """
    Pagination dependency with larger limits.
    For endpoints that commonly need more items (e.g., products).
    """
    return Pagination(limit=limit, offset=offset, max_limit=500)


def get_pagination_small(
    limit: int = Query(
        default=20,
        ge=1,
        le=50,
        description="Maximum number of items to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip",
    ),
) -> Pagination:
    """
    Pagination dependency with smaller limits.
    For endpoints with expensive queries (e.g., reports).
    """
    return Pagination(limit=limit, offset=offset, max_limit=50)


# =============================================================================
# Paginated Response Helper
# =============================================================================


@dataclass
class PaginatedResponse:
    """
    Wrapper for paginated responses.

    Usage:
        items = repo.find_all(tenant_id, filters)
        total = repo.count(tenant_id, filters)
        return PaginatedResponse(items=items, pagination=pagination, total=total)
    """

    items: list[Any]
    pagination: Pagination
    total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to response dictionary."""
        return {
            "items": self.items,
            "pagination": self.pagination.to_dict(self.total),
        }

    @property
    def has_more(self) -> bool:
        """Check if there are more items."""
        if self.total is None:
            return len(self.items) == self.pagination.limit
        return self.pagination.offset + len(self.items) < self.total
