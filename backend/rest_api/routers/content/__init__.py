"""
Content routers - Recipe management, ingredients, promotions, AI chatbot.
- /api/recipes/* - Recipe technical sheets
- /api/admin/ingredients/* - Ingredient management
- /api/admin/catalogs/* - Cooking methods, flavors, textures
- /api/admin/promotions/* - Promotions
- /api/rag/* - AI chatbot
"""

from .recipes import router as recipes_router
from .ingredients import router as ingredients_router
from .catalogs import router as catalogs_router
from .promotions import router as promotions_router
from .rag import router as rag_router

__all__ = [
    "recipes_router",
    "ingredients_router",
    "catalogs_router",
    "promotions_router",
    "rag_router",
]
