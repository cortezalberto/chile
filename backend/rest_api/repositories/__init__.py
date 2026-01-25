"""
Repository Pattern implementation.
HIGH-01 FIX: Centralizes data access with guaranteed eager loading.

Usage:
    from rest_api.repositories import ProductRepository, get_product_repository

    repo = get_product_repository(db)
    products = repo.find_all(tenant_id=1, filters=ProductFilters(category_id=5))
    product = repo.find_by_id(123, tenant_id=1)
"""

from .base import BaseRepository, RepositoryFilters
from .product import ProductRepository, ProductFilters, get_product_repository
from .category import CategoryRepository, CategoryFilters, get_category_repository
from .round import RoundRepository, RoundFilters, get_round_repository
from .kitchen_ticket import KitchenTicketRepository, TicketFilters, get_ticket_repository

__all__ = [
    # Base
    "BaseRepository",
    "RepositoryFilters",
    # Product
    "ProductRepository",
    "ProductFilters",
    "get_product_repository",
    # Category
    "CategoryRepository",
    "CategoryFilters",
    "get_category_repository",
    # Round
    "RoundRepository",
    "RoundFilters",
    "get_round_repository",
    # Kitchen Ticket
    "KitchenTicketRepository",
    "TicketFilters",
    "get_ticket_repository",
]
