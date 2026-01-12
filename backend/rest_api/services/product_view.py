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
"""

from typing import Optional, TypedDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, joinedload

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
            ProductAllergen.is_active == True,
            Allergen.is_active == True,
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
            ProductDietaryProfile.is_active == True,
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
            ProductIngredient.is_active == True,
            Ingredient.is_active == True,
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
            ProductCooking.is_active == True,
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
            ProductModification.is_active == True,
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
            ProductWarning.is_active == True,
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
            ProductRAGConfig.is_active == True,
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
            Product.is_active == True,
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
            BranchProduct.is_active == True,
            Product.is_active == True,
        )
    ).scalars().all()

    # Get complete view for each product
    results = []
    for product_id in product_ids:
        view = get_product_complete(db, product_id)
        if view:
            results.append(view)

    return results


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
