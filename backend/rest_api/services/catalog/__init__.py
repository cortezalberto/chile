"""
Catalog Services - Product catalog and content management.

Provides:
- Product view service with Redis caching
- RAG text generation for products and recipes
- Recipe-to-product synchronization
"""

from .product_view import (
    # Type definitions (TypedDict classes)
    AllergenInfo,
    AllergensView,
    DietaryProfileView,
    SubIngredientView,
    IngredientView,
    CookingView,
    SensoryView,
    ModificationView,
    WarningView,
    RAGConfigView,
    ProductCompleteView,
    # Core functions
    get_product_complete,
    get_products_complete_for_branch,
    get_products_complete_for_branch_cached,
    invalidate_branch_products_cache,
    invalidate_all_branch_caches_for_tenant,
    # RAG text generation
    generate_product_text_for_rag,
    generate_recipe_text_for_rag,
)
from .recipe_sync import (
    sync_product_from_recipe,
    derive_product_from_recipe,
    sync_all_products_for_recipe,
    get_recipe_product_summary,
)

__all__ = [
    # Product view types
    "AllergenInfo",
    "AllergensView",
    "DietaryProfileView",
    "SubIngredientView",
    "IngredientView",
    "CookingView",
    "SensoryView",
    "ModificationView",
    "WarningView",
    "RAGConfigView",
    "ProductCompleteView",
    # Product view functions
    "get_product_complete",
    "get_products_complete_for_branch",
    "get_products_complete_for_branch_cached",
    "invalidate_branch_products_cache",
    "invalidate_all_branch_caches_for_tenant",
    # RAG text generation
    "generate_product_text_for_rag",
    "generate_recipe_text_for_rag",
    # Recipe sync
    "sync_product_from_recipe",
    "derive_product_from_recipe",
    "sync_all_products_for_recipe",
    "get_recipe_product_summary",
]
