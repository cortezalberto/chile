"""
SQLAlchemy ORM Models Package.

All models are organized into domain-specific modules:
- base: Base class and AuditMixin
- tenant: Tenant, Branch
- user: User, UserBranchRole
- catalog: Category, Subcategory, Product, BranchProduct
- allergen: Allergen, ProductAllergen, AllergenCrossReaction
- ingredient: IngredientGroup, Ingredient, SubIngredient, ProductIngredient
- product_profile: Dietary, cooking, flavor, texture profiles
- sector: BranchSector, WaiterSectorAssignment
- table: Table, TableSession
- customer: Customer, Diner
- order: Round, RoundItem
- kitchen: KitchenTicket, KitchenTicketItem, ServiceCall
- billing: Check, Payment, Charge, Allocation
- knowledge: KnowledgeDocument, ChatLog (RAG)
- promotion: Promotion, PromotionBranch, PromotionItem
- exclusion: BranchCategoryExclusion, BranchSubcategoryExclusion
- audit: AuditLog
- recipe: Recipe, RecipeAllergen
"""

# Base classes
from .base import Base, AuditMixin

# Core tenant models
from .tenant import Tenant, Branch

# User and roles
from .user import User, UserBranchRole

# Catalog (menu structure)
from .catalog import Category, Subcategory, Product, BranchProduct

# Allergens
from .allergen import Allergen, ProductAllergen, AllergenCrossReaction

# Ingredients
from .ingredient import IngredientGroup, Ingredient, SubIngredient, ProductIngredient

# Product profiles (dietary, cooking, flavor, texture)
from .product_profile import (
    ProductDietaryProfile,
    CookingMethod,
    FlavorProfile,
    TextureProfile,
    CuisineType,
    ProductCookingMethod,
    ProductFlavor,
    ProductTexture,
    ProductCooking,
    ProductModification,
    ProductWarning,
    ProductRAGConfig,
)

# Branch sectors and waiter assignments
from .sector import BranchSector, WaiterSectorAssignment

# Tables and sessions
from .table import Table, TableSession

# Customers and diners
from .customer import Customer, Diner

# Cart (real-time shared cart)
from .cart import CartItem

# Orders (rounds)
from .order import Round, RoundItem

# Kitchen
from .kitchen import KitchenTicket, KitchenTicketItem, ServiceCall

# Billing
from .billing import Check, Payment, Charge, Allocation

# RAG knowledge base
from .knowledge import KnowledgeDocument, ChatLog

# Promotions
from .promotion import Promotion, PromotionBranch, PromotionItem

# Branch exclusions
from .exclusion import BranchCategoryExclusion, BranchSubcategoryExclusion

# Audit log
from .audit import AuditLog

# Recipes
from .recipe import Recipe, RecipeAllergen

__all__ = [
    # Base
    "Base",
    "AuditMixin",
    # Tenant
    "Tenant",
    "Branch",
    # User
    "User",
    "UserBranchRole",
    # Catalog
    "Category",
    "Subcategory",
    "Product",
    "BranchProduct",
    # Allergen
    "Allergen",
    "ProductAllergen",
    "AllergenCrossReaction",
    # Ingredient
    "IngredientGroup",
    "Ingredient",
    "SubIngredient",
    "ProductIngredient",
    # Product profiles
    "ProductDietaryProfile",
    "CookingMethod",
    "FlavorProfile",
    "TextureProfile",
    "CuisineType",
    "ProductCookingMethod",
    "ProductFlavor",
    "ProductTexture",
    "ProductCooking",
    "ProductModification",
    "ProductWarning",
    "ProductRAGConfig",
    # Sector
    "BranchSector",
    "WaiterSectorAssignment",
    # Table
    "Table",
    "TableSession",
    # Customer
    "Customer",
    "Diner",
    # Cart
    "CartItem",
    # Order
    "Round",
    "RoundItem",
    # Kitchen
    "KitchenTicket",
    "KitchenTicketItem",
    "ServiceCall",
    # Billing
    "Check",
    "Payment",
    "Charge",
    "Allocation",
    # Knowledge
    "KnowledgeDocument",
    "ChatLog",
    # Promotion
    "Promotion",
    "PromotionBranch",
    "PromotionItem",
    # Exclusion
    "BranchCategoryExclusion",
    "BranchSubcategoryExclusion",
    # Audit
    "AuditLog",
    # Recipe
    "Recipe",
    "RecipeAllergen",
]
