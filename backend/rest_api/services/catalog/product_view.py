"""
Consolidated product view service (Phase 5).

Provides a complete view of a product with all canonical model data:
- Allergens (contains, may_contain, free_from)
- Dietary profile (vegan, vegetarian, gluten-free, etc.)
- Ingredients (with sub-ingredients for processed items)
- Cooking methods and times
- Sensory profiles (flavors, textures)
- Modifications (allowed removals/substitutions)
- Warnings
- RAG configuration

This consolidated view is used by:
- pwaMenu for complete product information display
- RAG chatbot for enriched knowledge ingestion
- Public API endpoints

Enhanced with Redis caching (producto3.md improvement):
- get_products_complete_for_branch has 5-minute cache
- Cache invalidated on product update via invalidate_branch_products_cache()
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, joinedload

from shared.config.logging import get_logger

# IMPORT-01 FIX: Model imports at top of file
from rest_api.models import (
    Product,
    ProductAllergen,
    Allergen,
    ProductDietaryProfile,
    ProductIngredient,
    Ingredient,
    SubIngredient,
    ProductCooking,
    ProductCookingMethod,
    CookingMethod,
    ProductFlavor,
    FlavorProfile,
    ProductTexture,
    TextureProfile,
    ProductModification,
    ProductWarning,
    ProductRAGConfig,
    BranchProduct,
)

# TYPE-01 FIX: Import Recipe type for type hints
if TYPE_CHECKING:
    from rest_api.models import Recipe

logger = get_logger(__name__)


# =============================================================================
# DRY-01 FIX: Helper for safe JSON parsing
# =============================================================================


def _safe_json_parse(value: Optional[str], default: list | dict | None = None) -> list | dict | None:
    """
    Safely parse a JSON string, returning default on failure.

    DRY-01 FIX: Extracted from repeated try/except patterns in generate_recipe_text_for_rag.

    Args:
        value: JSON string to parse, or None
        default: Value to return on parse failure (default: None)

    Returns:
        Parsed JSON value, or default if parsing fails or value is None/empty
    """
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if parsed else default
    except (json.JSONDecodeError, TypeError):
        return default


# =============================================================================
# Redis Cache Configuration
# =============================================================================

# Cache TTL: 5 minutes for branch product views
CACHE_TTL_SECONDS = 5 * 60

def _get_branch_products_cache_key(branch_id: int, tenant_id: int) -> str:
    """
    MED-03 FIX: Generate Redis cache key for branch products.
    SVC-MED-03 FIX: Added defensive validation of inputs.

    Args:
        branch_id: Branch ID to include in the key (must be positive int)
        tenant_id: Tenant ID for multi-tenant isolation (must be positive int)

    Returns:
        Formatted cache key string: "branch:{branch_id}:tenant:{tenant_id}:products_complete"

    Raises:
        ValueError: If branch_id or tenant_id are invalid
    """
    # SVC-MED-03 FIX: Defensive validation
    if not isinstance(branch_id, int) or branch_id <= 0:
        raise ValueError(f"Invalid branch_id: {branch_id}")
    if not isinstance(tenant_id, int) or tenant_id <= 0:
        raise ValueError(f"Invalid tenant_id: {tenant_id}")

    return f"branch:{branch_id}:tenant:{tenant_id}:products_complete"


# =============================================================================
# Type definitions for the consolidated view
# =============================================================================


class AllergenInfo(TypedDict):
    id: int
    name: str
    icon: Optional[str]


class AllergensView(TypedDict):
    contains: list[AllergenInfo]
    may_contain: list[AllergenInfo]
    free_from: list[AllergenInfo]


class DietaryProfileView(TypedDict):
    is_vegetarian: bool
    is_vegan: bool
    is_gluten_free: bool
    is_dairy_free: bool
    is_celiac_safe: bool
    is_keto: bool
    is_low_sodium: bool


class SubIngredientView(TypedDict):
    id: int
    name: str


class IngredientView(TypedDict):
    id: int
    name: str
    group_name: Optional[str]
    is_processed: bool
    is_main: bool
    notes: Optional[str]
    sub_ingredients: list[SubIngredientView]


class CookingView(TypedDict):
    methods: list[str]
    uses_oil: bool
    prep_time_minutes: Optional[int]
    cook_time_minutes: Optional[int]


class SensoryView(TypedDict):
    flavors: list[str]
    textures: list[str]


class ModificationView(TypedDict):
    id: int
    action: str  # "remove" or "substitute"
    item: str
    is_allowed: bool
    extra_cost_cents: int


class WarningView(TypedDict):
    id: int
    text: str
    severity: str  # "info", "warning", "danger"


class RAGConfigView(TypedDict):
    risk_level: str  # "low", "medium", "high"
    custom_disclaimer: Optional[str]
    highlight_allergens: bool


class ProductCompleteView(TypedDict):
    """Complete product view with all canonical model data."""
    id: int
    name: str
    description: Optional[str]
    image: Optional[str]
    category_id: int
    subcategory_id: Optional[int]
    featured: bool
    popular: bool
    badge: Optional[str]
    # Canonical model data
    allergens: AllergensView
    dietary: DietaryProfileView
    ingredients: list[IngredientView]
    cooking: CookingView
    sensory: SensoryView
    modifications: list[ModificationView]
    warnings: list[WarningView]
    rag_config: Optional[RAGConfigView]


# =============================================================================
# Service functions
# =============================================================================


def get_product_allergens(db: Session, product_id: int) -> AllergensView:
    """Get allergens for a product grouped by presence type."""
    result: AllergensView = {
        "contains": [],
        "may_contain": [],
        "free_from": [],
    }

    # Query product allergens with allergen details
    product_allergens = db.execute(
        select(ProductAllergen, Allergen)
        .join(Allergen, ProductAllergen.allergen_id == Allergen.id)
        .where(
            ProductAllergen.product_id == product_id,
            ProductAllergen.is_active.is_(True),
            Allergen.is_active.is_(True),
        )
    ).all()

    for pa, allergen in product_allergens:
        allergen_info: AllergenInfo = {
            "id": allergen.id,
            "name": allergen.name,
            "icon": allergen.icon,
        }

        presence = pa.presence_type
        if presence == "contains":
            result["contains"].append(allergen_info)
        elif presence == "may_contain":
            result["may_contain"].append(allergen_info)
        elif presence == "free_from":
            result["free_from"].append(allergen_info)

    return result


def get_product_dietary_profile(db: Session, product_id: int) -> DietaryProfileView:
    """Get dietary profile for a product."""
    profile = db.scalar(
        select(ProductDietaryProfile).where(
            ProductDietaryProfile.product_id == product_id,
            ProductDietaryProfile.is_active.is_(True),
        )
    )

    if profile:
        return {
            "is_vegetarian": profile.is_vegetarian,
            "is_vegan": profile.is_vegan,
            "is_gluten_free": profile.is_gluten_free,
            "is_dairy_free": profile.is_dairy_free,
            "is_celiac_safe": profile.is_celiac_safe,
            "is_keto": profile.is_keto,
            "is_low_sodium": profile.is_low_sodium,
        }

    # Default profile (all false)
    return {
        "is_vegetarian": False,
        "is_vegan": False,
        "is_gluten_free": False,
        "is_dairy_free": False,
        "is_celiac_safe": False,
        "is_keto": False,
        "is_low_sodium": False,
    }


def get_product_ingredients(db: Session, product_id: int) -> list[IngredientView]:
    """Get ingredients for a product with their sub-ingredients."""
    product_ingredients = db.execute(
        select(ProductIngredient, Ingredient)
        .join(Ingredient, ProductIngredient.ingredient_id == Ingredient.id)
        .options(selectinload(Ingredient.sub_ingredients))
        .options(joinedload(Ingredient.group))
        .where(
            ProductIngredient.product_id == product_id,
            ProductIngredient.is_active.is_(True),
            Ingredient.is_active.is_(True),
        )
    ).unique().all()

    result: list[IngredientView] = []
    for pi, ingredient in product_ingredients:
        sub_ingredients: list[SubIngredientView] = []
        if ingredient.is_processed and ingredient.sub_ingredients:
            sub_ingredients = [
                {"id": si.id, "name": si.name}
                for si in ingredient.sub_ingredients
                if si.is_active
            ]

        result.append({
            "id": ingredient.id,
            "name": ingredient.name,
            "group_name": ingredient.group.name if ingredient.group else None,
            "is_processed": ingredient.is_processed,
            "is_main": pi.is_main,
            "notes": pi.notes,
            "sub_ingredients": sub_ingredients,
        })

    return result


def get_product_cooking(db: Session, product_id: int) -> CookingView:
    """Get cooking information for a product."""
    # Get cooking methods
    methods_query = db.execute(
        select(CookingMethod.name)
        .join(ProductCookingMethod, CookingMethod.id == ProductCookingMethod.cooking_method_id)
        .where(ProductCookingMethod.product_id == product_id)
    )
    methods = [row[0] for row in methods_query]

    # Get cooking info
    cooking_info = db.scalar(
        select(ProductCooking).where(
            ProductCooking.product_id == product_id,
            ProductCooking.is_active.is_(True),
        )
    )

    return {
        "methods": methods,
        "uses_oil": cooking_info.uses_oil if cooking_info else False,
        "prep_time_minutes": cooking_info.prep_time_minutes if cooking_info else None,
        "cook_time_minutes": cooking_info.cook_time_minutes if cooking_info else None,
    }


def get_product_sensory(db: Session, product_id: int) -> SensoryView:
    """Get sensory profile (flavors and textures) for a product."""
    # Get flavors
    flavors_query = db.execute(
        select(FlavorProfile.name)
        .join(ProductFlavor, FlavorProfile.id == ProductFlavor.flavor_profile_id)
        .where(ProductFlavor.product_id == product_id)
    )
    flavors = [row[0] for row in flavors_query]

    # Get textures
    textures_query = db.execute(
        select(TextureProfile.name)
        .join(ProductTexture, TextureProfile.id == ProductTexture.texture_profile_id)
        .where(ProductTexture.product_id == product_id)
    )
    textures = [row[0] for row in textures_query]

    return {
        "flavors": flavors,
        "textures": textures,
    }


def get_product_modifications(db: Session, product_id: int) -> list[ModificationView]:
    """Get allowed modifications for a product."""
    modifications = db.execute(
        select(ProductModification).where(
            ProductModification.product_id == product_id,
            ProductModification.is_active.is_(True),
        )
    ).scalars().all()

    return [
        {
            "id": m.id,
            "action": m.action,
            "item": m.item,
            "is_allowed": m.is_allowed,
            "extra_cost_cents": m.extra_cost_cents,
        }
        for m in modifications
    ]


def get_product_warnings(db: Session, product_id: int) -> list[WarningView]:
    """Get warnings for a product."""
    warnings = db.execute(
        select(ProductWarning).where(
            ProductWarning.product_id == product_id,
            ProductWarning.is_active.is_(True),
        )
    ).scalars().all()

    return [
        {
            "id": w.id,
            "text": w.text,
            "severity": w.severity,
        }
        for w in warnings
    ]


def get_product_rag_config(db: Session, product_id: int) -> Optional[RAGConfigView]:
    """Get RAG chatbot configuration for a product."""
    config = db.scalar(
        select(ProductRAGConfig).where(
            ProductRAGConfig.product_id == product_id,
            ProductRAGConfig.is_active.is_(True),
        )
    )

    if config:
        return {
            "risk_level": config.risk_level,
            "custom_disclaimer": config.custom_disclaimer,
            "highlight_allergens": config.highlight_allergens,
        }

    return None


def get_product_complete(db: Session, product_id: int) -> Optional[ProductCompleteView]:
    """
    Get complete product view with all canonical model data.

    This is the main function used by pwaMenu and RAG for complete product information.

    MED-29-07 NOTE: This function makes multiple DB queries per product (allergens, dietary,
    ingredients, cooking, sensory, modifications, warnings, rag_config). When called in a loop
    via get_products_complete_for_branch(), this creates an N+1 query pattern. However, this
    is mitigated by the Redis cache in get_products_complete_for_branch_cached() which caches
    the results for 5 minutes, avoiding repeated DB hits for the same branch.

    Args:
        db: Database session
        product_id: Product ID to fetch

    Returns:
        Complete product view or None if product not found
    """
    # Get base product
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_active.is_(True),
        )
    )

    if not product:
        return None

    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "image": product.image,
        "category_id": product.category_id,
        "subcategory_id": product.subcategory_id,
        "featured": product.featured,
        "popular": product.popular,
        "badge": product.badge,
        "allergens": get_product_allergens(db, product_id),
        "dietary": get_product_dietary_profile(db, product_id),
        "ingredients": get_product_ingredients(db, product_id),
        "cooking": get_product_cooking(db, product_id),
        "sensory": get_product_sensory(db, product_id),
        "modifications": get_product_modifications(db, product_id),
        "warnings": get_product_warnings(db, product_id),
        "rag_config": get_product_rag_config(db, product_id),
    }


def get_products_complete_for_branch(
    db: Session,
    branch_id: int,
    tenant_id: int,
) -> list[ProductCompleteView]:
    """
    Get complete views for all active products available in a branch.

    Args:
        db: Database session
        branch_id: Branch ID to filter by
        tenant_id: Tenant ID for security

    Returns:
        List of complete product views
    """
    # Get available product IDs in this branch
    product_ids = db.execute(
        select(BranchProduct.product_id)
        .join(Product, BranchProduct.product_id == Product.id)
        .where(
            BranchProduct.branch_id == branch_id,
            BranchProduct.tenant_id == tenant_id,
            BranchProduct.is_available == True,
            BranchProduct.is_active.is_(True),
            Product.is_active.is_(True),
        )
    ).scalars().all()

    # MED-29-07 NOTE: This loop calls get_product_complete() per product, creating N+1 queries.
    # This is mitigated by the Redis cache in get_products_complete_for_branch_cached() which
    # should be used in production. Direct calls to this function bypass the cache.
    # Get complete view for each product
    results = []
    for product_id in product_ids:
        view = get_product_complete(db, product_id)
        if view:
            results.append(view)

    return results


async def get_products_complete_for_branch_cached(
    db: Session,
    branch_id: int,
    tenant_id: int,
) -> list[ProductCompleteView]:
    """
    Get complete views for all active products with Redis caching.

    producto3.md improvement: Cache branch product views for 5 minutes.
    Falls back to database query if Redis is unavailable.

    Args:
        db: Database session
        branch_id: Branch ID to filter by
        tenant_id: Tenant ID for security

    Returns:
        List of complete product views (from cache or database)
    """
    from shared.infrastructure.events import get_redis_pool

    cache_key = _get_branch_products_cache_key(branch_id, tenant_id)

    # LOG-01 FIX: Use structured logging instead of f-strings
    try:
        redis = await get_redis_pool()
        cached = await redis.get(cache_key)

        if cached:
            logger.debug("Cache HIT for branch products", branch_id=branch_id)
            return json.loads(cached)

        logger.debug("Cache MISS for branch products", branch_id=branch_id)
    except Exception as e:
        logger.warning("Redis cache error, falling back to DB", error=str(e), branch_id=branch_id)
        # Fall through to database query

    # Query from database
    results = get_products_complete_for_branch(db, branch_id, tenant_id)

    # Cache the results
    try:
        redis = await get_redis_pool()
        await redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(results))
        logger.debug("Cached products for branch", count=len(results), branch_id=branch_id)
    except Exception as e:
        logger.warning("Failed to cache branch products", error=str(e), branch_id=branch_id)

    return results


async def invalidate_branch_products_cache(branch_id: int, tenant_id: int) -> bool:
    """
    Invalidate the cached product views for a branch.

    Call this when:
    - A product is created, updated, or deleted
    - A BranchProduct is updated (availability, price)
    - Allergen or ingredient data is modified

    Args:
        branch_id: Branch ID to invalidate
        tenant_id: Tenant ID for security

    Returns:
        True if cache was invalidated, False on error
    """
    from shared.infrastructure.events import get_redis_pool

    cache_key = _get_branch_products_cache_key(branch_id, tenant_id)

    # LOG-01 FIX: Use structured logging instead of f-strings
    try:
        redis = await get_redis_pool()
        result = await redis.delete(cache_key)
        logger.info("Invalidated cache for branch", branch_id=branch_id, deleted=result)
        return True
    except Exception as e:
        logger.warning("Failed to invalidate branch cache", error=str(e), branch_id=branch_id)
        return False


async def invalidate_all_branch_caches_for_tenant(tenant_id: int) -> int:
    """
    Invalidate all cached product views for a tenant.

    Call this when tenant-wide changes occur (e.g., allergen renamed).

    SVC-MED-08 FIX: Added limit to scan_iter to prevent unbounded result set.

    Args:
        tenant_id: Tenant ID

    Returns:
        Number of cache keys deleted
    """
    from shared.infrastructure.events import get_redis_pool

    # SVC-MED-08 FIX: Limit maximum keys to delete in one operation
    MAX_KEYS_PER_OPERATION = 1000

    # LOG-01 FIX: Use structured logging instead of f-strings
    try:
        redis = await get_redis_pool()
        pattern = f"branch:*:tenant:{tenant_id}:products_complete"
        keys = []
        # SVC-MED-08 FIX: Use count parameter to limit batch size and cap total
        async for key in redis.scan_iter(pattern, count=100):
            keys.append(key)
            if len(keys) >= MAX_KEYS_PER_OPERATION:
                logger.warning(
                    "Hit max keys limit for tenant cache invalidation",
                    max_keys=MAX_KEYS_PER_OPERATION,
                    tenant_id=tenant_id,
                )
                break

        if keys:
            deleted = await redis.delete(*keys)
            logger.info("Invalidated branch caches for tenant", deleted=deleted, tenant_id=tenant_id)
            return deleted
        return 0
    except Exception as e:
        logger.warning("Failed to invalidate tenant caches", error=str(e), tenant_id=tenant_id)
        return 0


# =============================================================================
# Text generation for RAG ingestion
# =============================================================================


def generate_product_text_for_rag(view: ProductCompleteView, price_cents: Optional[int] = None) -> str:
    """
    Generate enriched text description of a product for RAG ingestion.

    This function creates a detailed text representation including all
    canonical model data, optimized for semantic search and LLM understanding.

    Args:
        view: Complete product view
        price_cents: Optional price in cents for this branch

    Returns:
        Rich text description suitable for RAG knowledge base
    """
    lines = []

    # Basic info
    lines.append(f"PRODUCTO: {view['name']}")

    if view['description']:
        lines.append(f"Descripción: {view['description']}")

    if price_cents is not None:
        price_str = f"${price_cents / 100:.2f}"
        lines.append(f"Precio: {price_str}")

    if view['badge']:
        lines.append(f"Insignia: {view['badge']}")

    # Allergens (critical for safety)
    allergens = view['allergens']
    if allergens['contains']:
        names = [a['name'] for a in allergens['contains']]
        lines.append(f"CONTIENE ALÉRGENOS: {', '.join(names)}")

    if allergens['may_contain']:
        names = [a['name'] for a in allergens['may_contain']]
        lines.append(f"PUEDE CONTENER TRAZAS DE: {', '.join(names)}")

    if allergens['free_from']:
        names = [a['name'] for a in allergens['free_from']]
        lines.append(f"Libre de: {', '.join(names)}")

    # Dietary profile
    dietary = view['dietary']
    dietary_tags = []
    if dietary['is_vegan']:
        dietary_tags.append("Vegano")
    if dietary['is_vegetarian'] and not dietary['is_vegan']:
        dietary_tags.append("Vegetariano")
    if dietary['is_gluten_free']:
        dietary_tags.append("Sin Gluten")
    if dietary['is_celiac_safe']:
        dietary_tags.append("Apto Celíacos")
    if dietary['is_dairy_free']:
        dietary_tags.append("Sin Lácteos")
    if dietary['is_keto']:
        dietary_tags.append("Keto")
    if dietary['is_low_sodium']:
        dietary_tags.append("Bajo en Sodio")

    if dietary_tags:
        lines.append(f"Perfil dietético: {', '.join(dietary_tags)}")

    # Ingredients
    if view['ingredients']:
        main_ingredients = [i['name'] for i in view['ingredients'] if i['is_main']]
        other_ingredients = [i['name'] for i in view['ingredients'] if not i['is_main']]

        if main_ingredients:
            lines.append(f"Ingredientes principales: {', '.join(main_ingredients)}")
        if other_ingredients:
            lines.append(f"Otros ingredientes: {', '.join(other_ingredients)}")

    # Cooking info
    cooking = view['cooking']
    if cooking['methods']:
        lines.append(f"Métodos de cocción: {', '.join(cooking['methods'])}")

    if cooking['uses_oil']:
        lines.append("Preparación: Utiliza aceite en la cocción")

    if cooking['prep_time_minutes'] or cooking['cook_time_minutes']:
        total_time = (cooking['prep_time_minutes'] or 0) + (cooking['cook_time_minutes'] or 0)
        lines.append(f"Tiempo de preparación: {total_time} minutos aprox.")

    # Sensory profile
    sensory = view['sensory']
    if sensory['flavors']:
        lines.append(f"Sabor: {', '.join(sensory['flavors'])}")
    if sensory['textures']:
        lines.append(f"Textura: {', '.join(sensory['textures'])}")

    # Modifications
    if view['modifications']:
        allowed_mods = [m for m in view['modifications'] if m['is_allowed']]
        if allowed_mods:
            mod_texts = []
            for m in allowed_mods:
                if m['action'] == 'remove':
                    mod_texts.append(f"Se puede quitar: {m['item']}")
                else:  # substitute
                    mod_texts.append(f"Se puede sustituir: {m['item']}")
            lines.append("Modificaciones permitidas: " + "; ".join(mod_texts))

    # Warnings
    if view['warnings']:
        for w in view['warnings']:
            prefix = "⚠️ " if w['severity'] in ('warning', 'danger') else "ℹ️ "
            lines.append(f"{prefix}Advertencia: {w['text']}")

    # RAG config disclaimers
    if view['rag_config'] and view['rag_config']['custom_disclaimer']:
        lines.append(f"Nota importante: {view['rag_config']['custom_disclaimer']}")

    return "\n".join(lines)


# =============================================================================
# Recipe text generation for RAG ingestion
# =============================================================================


def generate_recipe_text_for_rag(
    recipe: Recipe,
    allergens: list[dict] | None = None,
) -> str:
    """
    Generate enriched text description of a recipe for RAG ingestion.

    This function creates a detailed text representation including all
    recipe data, optimized for semantic search and LLM understanding.

    The generated text enables the chatbot to answer questions like:
    - "¿Cómo se prepara la milanesa napolitana?"
    - "¿Qué ingredientes tiene el tiramisú?"
    - "¿Cuánto tiempo tarda el risotto?"
    - "¿Es apto para celíacos?"

    Args:
        recipe: Recipe model instance
        allergens: Optional list of allergen dicts with 'id', 'name', 'icon'

    Returns:
        Rich text description suitable for RAG knowledge base
    """
    lines = []

    # Basic info
    lines.append(f"RECETA: {recipe.name}")

    if recipe.short_description:
        lines.append(f"Resumen: {recipe.short_description}")

    if recipe.description:
        lines.append(f"Descripción completa: {recipe.description}")

    # Cuisine and difficulty
    if recipe.cuisine_type:
        lines.append(f"Tipo de cocina: {recipe.cuisine_type}")

    if recipe.difficulty:
        difficulty_labels = {"EASY": "Fácil", "MEDIUM": "Media", "HARD": "Difícil"}
        lines.append(f"Dificultad: {difficulty_labels.get(recipe.difficulty, recipe.difficulty)}")

    # Time information
    if recipe.prep_time_minutes:
        lines.append(f"Tiempo de preparación: {recipe.prep_time_minutes} minutos")

    if recipe.cook_time_minutes:
        lines.append(f"Tiempo de cocción: {recipe.cook_time_minutes} minutos")

    if recipe.prep_time_minutes or recipe.cook_time_minutes:
        total = (recipe.prep_time_minutes or 0) + (recipe.cook_time_minutes or 0)
        lines.append(f"Tiempo total: {total} minutos")

    # Servings and calories
    if recipe.servings:
        lines.append(f"Porciones: {recipe.servings}")

    if recipe.calories_per_serving:
        lines.append(f"Calorías por porción: {recipe.calories_per_serving} kcal")

    # DRY-01 FIX: Use _safe_json_parse helper instead of repeated try/except blocks
    # Ingredients (detailed)
    ingredients = _safe_json_parse(recipe.ingredients, [])
    if ingredients:
        lines.append("INGREDIENTES:")
        for ing in ingredients:
            name = ing.get('name', '')
            quantity = ing.get('quantity', '')
            unit = ing.get('unit', '')
            notes = ing.get('notes', '')
            ing_line = f"  - {name}: {quantity} {unit}".strip()
            if notes:
                ing_line += f" ({notes})"
            lines.append(ing_line)

    # Preparation steps
    steps = _safe_json_parse(recipe.preparation_steps, [])
    if steps:
        lines.append("PREPARACIÓN:")
        for step in sorted(steps, key=lambda s: s.get('step', 0)):
            step_num = step.get('step', 0)
            instruction = step.get('instruction', '')
            time_mins = step.get('time_minutes')
            step_line = f"  Paso {step_num}: {instruction}"
            if time_mins:
                step_line += f" ({time_mins} min)"
            lines.append(step_line)

    # Allergens (critical for safety)
    if allergens:
        allergen_names = [a.get('name', '') for a in allergens if a.get('name')]
        if allergen_names:
            lines.append(f"CONTIENE ALÉRGENOS: {', '.join(allergen_names)}")

    # Dietary tags
    dietary = _safe_json_parse(recipe.dietary_tags, [])
    if dietary:
        lines.append(f"Perfil dietético: {', '.join(dietary)}")

    # Celiac safety (special flag)
    if recipe.is_celiac_safe:
        lines.append("✅ APTO CELÍACO: Preparado con protocolos especiales para celíacos")

    # Cooking methods
    methods = _safe_json_parse(recipe.cooking_methods, [])
    if methods:
        lines.append(f"Métodos de cocción: {', '.join(methods)}")

    if recipe.uses_oil:
        lines.append("Preparación: Utiliza aceite en la cocción")

    # Sensory profile - flavors
    flavors = _safe_json_parse(recipe.flavors, [])
    if flavors:
        lines.append(f"Perfil de sabor: {', '.join(flavors)}")

    # Sensory profile - textures
    textures = _safe_json_parse(recipe.textures, [])
    if textures:
        lines.append(f"Perfil de textura: {', '.join(textures)}")

    # Modifications allowed
    mods = _safe_json_parse(recipe.modifications, [])
    if mods:
        allowed = [m for m in mods if m.get('allowed', True)]
        if allowed:
            mod_texts = []
            for m in allowed:
                action = m.get('action', '')
                item = m.get('item', '')
                if action == 'remove':
                    mod_texts.append(f"Se puede quitar: {item}")
                elif action == 'substitute':
                    mod_texts.append(f"Se puede sustituir: {item}")
            if mod_texts:
                lines.append("Modificaciones permitidas: " + "; ".join(mod_texts))

    # Warnings
    warnings_list = _safe_json_parse(recipe.warnings, [])
    if warnings_list:
        for warning in warnings_list:
            lines.append(f"⚠️ Advertencia: {warning}")

    # Chef notes
    if recipe.chef_notes:
        lines.append(f"Notas del chef: {recipe.chef_notes}")

    # Presentation tips
    if recipe.presentation_tips:
        lines.append(f"Tips de presentación: {recipe.presentation_tips}")

    # Storage instructions
    if recipe.storage_instructions:
        lines.append(f"Almacenamiento: {recipe.storage_instructions}")

    # Allergen notes
    if recipe.allergen_notes:
        lines.append(f"Notas sobre alérgenos: {recipe.allergen_notes}")

    # Yield and portion info
    if recipe.yield_quantity and recipe.yield_unit:
        lines.append(f"Rendimiento: {recipe.yield_quantity} {recipe.yield_unit}")

    if recipe.portion_size:
        lines.append(f"Tamaño de porción: {recipe.portion_size}")

    # Cost information (useful for the chatbot to answer about value)
    if recipe.suggested_price_cents:
        price_str = f"${recipe.suggested_price_cents / 100:.2f}"
        lines.append(f"Precio sugerido: {price_str}")

    # RAG risk level and disclaimer
    lines.append(f"NIVEL DE RIESGO NUTRICIONAL: {recipe.risk_level or 'low'}")

    if recipe.custom_rag_disclaimer:
        lines.append(f"Nota importante: {recipe.custom_rag_disclaimer}")

    return "\n".join(lines)
