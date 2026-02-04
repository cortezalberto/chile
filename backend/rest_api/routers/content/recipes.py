"""
Recipes router.
CRUD operations for recipe technical sheets.
Accessible by KITCHEN, MANAGER, and ADMIN roles.
"""

import json
from datetime import datetime, timezone
# LOW-01 FIX: Removed unused Optional import
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select

from shared.infrastructure.db import get_db
from rest_api.models import Recipe, Product, Branch, Category, Subcategory, Allergen, RecipeAllergen
from shared.security.auth import current_user_context, require_roles
from shared.utils.validators import validate_image_url
from rest_api.services.crud.soft_delete import (
    soft_delete,
    set_created_by,
    set_updated_by,
)
from rest_api.routers._common.base import get_user_id, get_user_email
from shared.config.logging import rest_api_logger as logger


router = APIRouter(prefix="/api/recipes", tags=["recipes"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class IngredientItem(BaseModel):
    ingredient_id: int | None = None  # Optional reference to Ingredient table
    name: str                          # Display name (from selected ingredient or manual)
    quantity: str
    unit: str
    notes: str | None = None


class PreparationStep(BaseModel):
    step: int
    instruction: str
    time_minutes: int | None = None


class ModificationItem(BaseModel):
    """Modification allowed/disallowed for a recipe."""
    action: str  # "remove" or "substitute"
    item: str    # What can be removed/substituted
    allowed: bool = True


class AllergenInfo(BaseModel):
    """Allergen info returned from API."""
    id: int
    name: str
    icon: str | None = None


class RecipeCreate(BaseModel):
    branch_id: int
    name: str = Field(..., min_length=2, max_length=200)  # QA-LOW-02 FIX: Add length validation
    description: str | None = Field(None, max_length=2000)
    short_description: str | None = Field(None, max_length=200)  # Short description for preview (100-150 chars)
    image: str | None = Field(None, max_length=500)
    product_id: int | None = None
    subcategory_id: int | None = None  # Links to subcategory which has category
    cuisine_type: str | None = None
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    calories_per_serving: int | None = None
    ingredients: list[IngredientItem] | None = None
    preparation_steps: list[PreparationStep] | None = None
    chef_notes: str | None = None
    presentation_tips: str | None = None
    storage_instructions: str | None = None
    allergen_ids: list[int] | None = None  # M:N relation via RecipeAllergen
    dietary_tags: list[str] | None = None
    # Sensory profile (Phase 3 - planteo.md)
    flavors: list[str] | None = None  # ["suave", "intenso", "dulce", "salado", "acido", "amargo", "umami", "picante"]
    textures: list[str] | None = None  # ["crocante", "cremoso", "tierno", "firme", "esponjoso", "gelatinoso", "granulado"]
    # Cooking info
    cooking_methods: list[str] | None = None  # ["horneado", "frito", "grillado", "crudo", "hervido", "vapor", "salteado", "braseado"]
    uses_oil: bool = False
    # Celiac safety
    is_celiac_safe: bool = False
    allergen_notes: str | None = None
    # Modifications and warnings (Phase 4 - planteo.md)
    modifications: list[ModificationItem] | None = None
    warnings: list[str] | None = None
    # Cost and yield
    cost_cents: int | None = None
    suggested_price_cents: int | None = None
    yield_quantity: str | None = None  # e.g., "2kg", "24 unidades"
    yield_unit: str | None = None
    portion_size: str | None = None  # e.g., "200g", "1 unidad"
    # RAG config (Phase 5 - planteo.md)
    risk_level: str = "low"  # low, medium, high
    custom_rag_disclaimer: str | None = None


class RecipeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    image: str | None = None
    product_id: int | None = None
    subcategory_id: int | None = None
    cuisine_type: str | None = None
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int | None = None
    calories_per_serving: int | None = None
    ingredients: list[IngredientItem] | None = None
    preparation_steps: list[PreparationStep] | None = None
    chef_notes: str | None = None
    presentation_tips: str | None = None
    storage_instructions: str | None = None
    allergen_ids: list[int] | None = None  # M:N relation via RecipeAllergen
    dietary_tags: list[str] | None = None
    # Sensory profile
    flavors: list[str] | None = None
    textures: list[str] | None = None
    # Cooking info
    cooking_methods: list[str] | None = None
    uses_oil: bool | None = None
    # Celiac safety
    is_celiac_safe: bool | None = None
    allergen_notes: str | None = None
    # Modifications and warnings
    modifications: list[ModificationItem] | None = None
    warnings: list[str] | None = None
    # Cost and yield
    cost_cents: int | None = None
    suggested_price_cents: int | None = None
    yield_quantity: str | None = None
    yield_unit: str | None = None
    portion_size: str | None = None
    # RAG config
    risk_level: str | None = None
    custom_rag_disclaimer: str | None = None


class RecipeOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    branch_name: str | None = None
    name: str
    description: str | None = None
    short_description: str | None = None
    image: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    subcategory_id: int | None = None
    subcategory_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    cuisine_type: str | None = None
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    total_time_minutes: int | None = None
    servings: int | None = None
    calories_per_serving: int | None = None
    ingredients: list[IngredientItem] | None = None
    preparation_steps: list[PreparationStep] | None = None
    chef_notes: str | None = None
    presentation_tips: str | None = None
    storage_instructions: str | None = None
    allergen_ids: list[int] | None = None  # IDs for form binding
    allergens: list[AllergenInfo] | None = None  # Full allergen info for display
    dietary_tags: list[str] | None = None
    # Sensory profile
    flavors: list[str] | None = None
    textures: list[str] | None = None
    # Cooking info
    cooking_methods: list[str] | None = None
    uses_oil: bool = False
    # Celiac safety
    is_celiac_safe: bool = False
    allergen_notes: str | None = None
    # Modifications and warnings
    modifications: list[ModificationItem] | None = None
    warnings: list[str] | None = None
    # Cost and yield
    cost_cents: int | None = None
    suggested_price_cents: int | None = None
    yield_quantity: str | None = None
    yield_unit: str | None = None
    portion_size: str | None = None
    # RAG config
    risk_level: str = "low"
    custom_rag_disclaimer: str | None = None
    # Status
    is_active: bool
    is_ingested: bool
    last_ingested_at: datetime | None = None
    created_at: datetime
    created_by_email: str | None = None

    class Config:
        from_attributes = True


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_json_field(value: str | None, default: list | None = None) -> list | None:
    """Parse JSON string field to list."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _serialize_json_field(value: list | None) -> str | None:
    """Serialize list to JSON string."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _build_recipe_output(
    recipe: Recipe,
    branch: Branch | None = None,
    product: Product | None = None,
    subcategory: Subcategory | None = None,
    category: Category | None = None,
    recipe_allergens: list[tuple] | None = None,
) -> RecipeOutput:
    """
    Build RecipeOutput from Recipe model.

    AUDIT FIX: Now accepts pre-loaded relationships to avoid N+1 queries.
    When called from list_recipes(), all data is pre-loaded via eager loading.
    """
    # Use pre-loaded data if available
    branch_name = branch.name if branch else None
    product_name = product.name if product else None
    subcategory_name = subcategory.name if subcategory else None
    category_id = category.id if category else (subcategory.category_id if subcategory else None)
    category_name = category.name if category else None

    # Parse JSON fields
    ingredients = _parse_json_field(recipe.ingredients, [])
    preparation_steps = _parse_json_field(recipe.preparation_steps, [])
    dietary_tags = _parse_json_field(recipe.dietary_tags, [])
    flavors = _parse_json_field(recipe.flavors, [])
    textures = _parse_json_field(recipe.textures, [])
    cooking_methods = _parse_json_field(recipe.cooking_methods, [])
    modifications = _parse_json_field(recipe.modifications, [])
    warnings = _parse_json_field(recipe.warnings, [])

    # Use pre-loaded allergens if available
    if recipe_allergens is not None:
        allergen_ids = [ra.allergen_id for ra, alg in recipe_allergens]
        allergens = [
            AllergenInfo(id=alg.id, name=alg.name, icon=alg.icon)
            for ra, alg in recipe_allergens
        ]
    else:
        allergen_ids = []
        allergens = []

    # Calculate total time
    prep_time = recipe.prep_time_minutes or 0
    cook_time = recipe.cook_time_minutes or 0
    total_time = (prep_time + cook_time) if (prep_time or cook_time) else None

    return RecipeOutput(
        id=recipe.id,
        tenant_id=recipe.tenant_id,
        branch_id=recipe.branch_id,
        branch_name=branch_name,
        name=recipe.name,
        description=recipe.description,
        short_description=recipe.short_description,
        image=recipe.image,
        product_id=recipe.product_id,
        product_name=product_name,
        subcategory_id=recipe.subcategory_id,
        subcategory_name=subcategory_name,
        category_id=category_id,
        category_name=category_name,
        cuisine_type=recipe.cuisine_type,
        difficulty=recipe.difficulty,
        prep_time_minutes=recipe.prep_time_minutes,
        cook_time_minutes=recipe.cook_time_minutes,
        total_time_minutes=total_time,
        servings=recipe.servings,
        calories_per_serving=recipe.calories_per_serving,
        ingredients=ingredients,
        preparation_steps=preparation_steps,
        chef_notes=recipe.chef_notes,
        presentation_tips=recipe.presentation_tips,
        storage_instructions=recipe.storage_instructions,
        allergen_ids=allergen_ids,
        allergens=allergens,
        dietary_tags=dietary_tags,
        # Sensory profile
        flavors=flavors,
        textures=textures,
        # Cooking info
        cooking_methods=cooking_methods,
        uses_oil=recipe.uses_oil,
        # Celiac safety
        is_celiac_safe=recipe.is_celiac_safe,
        allergen_notes=recipe.allergen_notes,
        # Modifications and warnings
        modifications=modifications,
        warnings=warnings,
        # Cost and yield
        cost_cents=recipe.cost_cents,
        suggested_price_cents=recipe.suggested_price_cents,
        yield_quantity=recipe.yield_quantity,
        yield_unit=recipe.yield_unit,
        portion_size=recipe.portion_size,
        # RAG config
        risk_level=recipe.risk_level,
        custom_rag_disclaimer=recipe.custom_rag_disclaimer,
        # Status
        is_active=recipe.is_active,
        is_ingested=recipe.is_ingested,
        last_ingested_at=recipe.last_ingested_at,
        created_at=recipe.created_at,
        created_by_email=recipe.created_by_email,
    )


def _sync_recipe_allergens(
    db: Session,
    recipe: Recipe,
    allergen_ids: list[int] | None,
    tenant_id: int,
    user_id: int | None,
    user_email: str,
) -> None:
    """Sync recipe allergens - replace existing with new list."""
    if allergen_ids is None:
        return

    # Get current allergen IDs
    current_allergen_ids = set(
        db.scalars(
            select(RecipeAllergen.allergen_id).where(
                RecipeAllergen.recipe_id == recipe.id,
                RecipeAllergen.is_active.is_(True),
            )
        ).all()
    )
    new_allergen_ids = set(allergen_ids)

    # Remove allergens no longer in list
    ids_to_remove = current_allergen_ids - new_allergen_ids
    # CRIT-04 FIX: Batch soft-delete instead of individual queries
    if ids_to_remove:
        records_to_remove = db.scalars(
            select(RecipeAllergen).where(
                RecipeAllergen.recipe_id == recipe.id,
                RecipeAllergen.allergen_id.in_(ids_to_remove),
            )
        ).all()
        for ra in records_to_remove:
            ra.soft_delete(user_id or 0, user_email)

    # Add new allergens
    ids_to_add = new_allergen_ids - current_allergen_ids

    if ids_to_add:
        # CRIT-04 FIX: Batch validate allergens in one query
        valid_allergens = db.scalars(
            select(Allergen).where(
                Allergen.id.in_(ids_to_add),
                Allergen.tenant_id == tenant_id,
                Allergen.is_active.is_(True),
            )
        ).all()
        valid_allergen_ids = {a.id for a in valid_allergens}

        # CRIT-04 FIX: Batch fetch existing soft-deleted records
        existing_records = {
            ra.allergen_id: ra
            for ra in db.scalars(
                select(RecipeAllergen).where(
                    RecipeAllergen.recipe_id == recipe.id,
                    RecipeAllergen.allergen_id.in_(ids_to_add),
                    RecipeAllergen.is_active == False,
                )
            ).all()
        }

        for allergen_id in ids_to_add:
            if allergen_id not in valid_allergen_ids:
                continue  # Skip invalid allergen IDs silently

            existing = existing_records.get(allergen_id)
            if existing:
                existing.restore(user_id or 0, user_email)
            else:
                ra = RecipeAllergen(
                    tenant_id=tenant_id,
                    recipe_id=recipe.id,
                    allergen_id=allergen_id,
                )
                ra.set_created_by(user_id or 0, user_email)
                db.add(ra)


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[RecipeOutput])
def list_recipes(
    branch_id: int | None = None,
    category: str | None = None,
    include_deleted: bool = False,
    # RTR-MED-07 FIX: Added pagination support for large datasets
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[RecipeOutput]:
    """
    List recipes for the user's branches.

    KITCHEN: Can see recipes from their assigned branches
    MANAGER/ADMIN: Can see recipes from all their branches

    AUDIT FIX: Uses eager loading to prevent N+1 queries.
    RTR-MED-07 FIX: Added limit/offset pagination for performance with large datasets.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    if not user_branch_ids:
        return []

    query = select(Recipe).where(Recipe.tenant_id == tenant_id)

    if not include_deleted:
        query = query.where(Recipe.is_active.is_(True))

    # Filter by branch
    if branch_id:
        if branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a esta sucursal",
            )
        query = query.where(Recipe.branch_id == branch_id)
    else:
        query = query.where(Recipe.branch_id.in_(user_branch_ids))

    # Filter by category
    if category:
        query = query.where(Recipe.category == category)

    # RTR-MED-07 FIX: Apply pagination
    query = query.order_by(Recipe.name.asc()).offset(offset).limit(limit)
    recipes = db.execute(query).scalars().all()

    # AUDIT FIX: Batch load all related data to avoid N+1 queries
    recipe_ids = [r.id for r in recipes]
    branch_ids_list = list(set(r.branch_id for r in recipes))
    product_ids = [r.product_id for r in recipes if r.product_id]
    subcategory_ids = [r.subcategory_id for r in recipes if r.subcategory_id]

    # Load all branches at once
    branches_map = {}
    if branch_ids_list:
        branches = db.execute(
            select(Branch).where(Branch.id.in_(branch_ids_list))
        ).scalars().all()
        branches_map = {b.id: b for b in branches}

    # Load all products at once
    products_map = {}
    if product_ids:
        products = db.execute(
            select(Product).where(Product.id.in_(product_ids))
        ).scalars().all()
        products_map = {p.id: p for p in products}

    # Load all subcategories at once (with tenant validation)
    subcategories_map = {}
    if subcategory_ids:
        subcategories = db.execute(
            select(Subcategory).where(
                Subcategory.id.in_(subcategory_ids),
                Subcategory.tenant_id == tenant_id,
            )
        ).scalars().all()
        subcategories_map = {s.id: s for s in subcategories}

    # Load all categories at once
    category_ids_list = list(set(s.category_id for s in subcategories_map.values() if s.category_id))
    categories_map = {}
    if category_ids_list:
        categories = db.execute(
            select(Category).where(Category.id.in_(category_ids_list))
        ).scalars().all()
        categories_map = {c.id: c for c in categories}

    # Load all allergens at once
    allergens_map: dict[int, list[tuple]] = {rid: [] for rid in recipe_ids}
    if recipe_ids:
        recipe_allergen_rows = db.execute(
            select(RecipeAllergen, Allergen)
            .join(Allergen, RecipeAllergen.allergen_id == Allergen.id)
            .where(
                RecipeAllergen.recipe_id.in_(recipe_ids),
                RecipeAllergen.is_active.is_(True),
                Allergen.is_active.is_(True),
            )
        ).all()
        for ra, alg in recipe_allergen_rows:
            allergens_map[ra.recipe_id].append((ra, alg))

    # Build outputs with pre-loaded data
    result = []
    for r in recipes:
        branch = branches_map.get(r.branch_id)
        product = products_map.get(r.product_id) if r.product_id else None
        subcategory = subcategories_map.get(r.subcategory_id) if r.subcategory_id else None
        cat = categories_map.get(subcategory.category_id) if subcategory and subcategory.category_id else None
        recipe_allergens = allergens_map.get(r.id, [])

        result.append(_build_recipe_output(
            recipe=r,
            branch=branch,
            product=product,
            subcategory=subcategory,
            category=cat,
            recipe_allergens=recipe_allergens,
        ))

    return result


@router.get("/{recipe_id}", response_model=RecipeOutput)
def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> RecipeOutput:
    """Get a specific recipe by ID."""
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )
    )

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receta no encontrada",
        )

    if recipe.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta receta",
        )

    # AUDIT FIX: Load related data to avoid N+1 queries
    branch = db.scalar(select(Branch).where(
        Branch.id == recipe.branch_id,
        Branch.tenant_id == tenant_id,
    ))
    product = None
    if recipe.product_id:
        product = db.scalar(select(Product).where(
            Product.id == recipe.product_id,
            Product.tenant_id == tenant_id,
        ))
    subcategory = None
    category = None
    if recipe.subcategory_id:
        subcategory = db.scalar(select(Subcategory).where(
            Subcategory.id == recipe.subcategory_id,
            Subcategory.tenant_id == tenant_id,
        ))
        if subcategory and subcategory.category_id:
            category = db.scalar(select(Category).where(
                Category.id == subcategory.category_id
            ))

    # Load allergens
    recipe_allergens = db.execute(
        select(RecipeAllergen, Allergen)
        .join(Allergen, RecipeAllergen.allergen_id == Allergen.id)
        .where(
            RecipeAllergen.recipe_id == recipe.id,
            RecipeAllergen.is_active.is_(True),
            Allergen.is_active.is_(True),
        )
    ).all()

    return _build_recipe_output(
        recipe=recipe,
        branch=branch,
        product=product,
        subcategory=subcategory,
        category=category,
        recipe_allergens=recipe_allergens,
    )


@router.post("", response_model=RecipeOutput, status_code=status.HTTP_201_CREATED)
def create_recipe(
    body: RecipeCreate,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> RecipeOutput:
    """
    Create a new recipe.

    KITCHEN, MANAGER, ADMIN can create recipes in their branches.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    # Validate branch access
    if body.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta sucursal",
        )

    # Validate product exists if provided
    if body.product_id:
        product = db.scalar(
            select(Product).where(
                Product.id == body.product_id,
                Product.tenant_id == tenant_id,
            )
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Producto no encontrado",
            )

    # Validate subcategory exists if provided
    if body.subcategory_id:
        subcategory = db.scalar(
            select(Subcategory).where(
                Subcategory.id == body.subcategory_id,
                Subcategory.tenant_id == tenant_id,
                Subcategory.is_active.is_(True),
            )
        )
        if not subcategory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subcategoría no encontrada",
            )

    # HIGH-04 FIX: Validate image URL to prevent SSRF attacks
    validated_image = None
    if body.image:
        try:
            validated_image = validate_image_url(body.image)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    recipe = Recipe(
        tenant_id=tenant_id,
        branch_id=body.branch_id,
        name=body.name,
        description=body.description,
        short_description=body.short_description,
        image=validated_image,  # HIGH-04 FIX: Use validated image URL
        product_id=body.product_id,
        subcategory_id=body.subcategory_id,
        cuisine_type=body.cuisine_type,
        difficulty=body.difficulty,
        prep_time_minutes=body.prep_time_minutes,
        cook_time_minutes=body.cook_time_minutes,
        servings=body.servings,
        calories_per_serving=body.calories_per_serving,
        ingredients=_serialize_json_field([i.model_dump() for i in body.ingredients] if body.ingredients else None),
        preparation_steps=_serialize_json_field([s.model_dump() for s in body.preparation_steps] if body.preparation_steps else None),
        chef_notes=body.chef_notes,
        presentation_tips=body.presentation_tips,
        storage_instructions=body.storage_instructions,
        dietary_tags=_serialize_json_field(body.dietary_tags),
        # Sensory profile
        flavors=_serialize_json_field(body.flavors),
        textures=_serialize_json_field(body.textures),
        # Cooking info
        cooking_methods=_serialize_json_field(body.cooking_methods),
        uses_oil=body.uses_oil,
        # Celiac safety
        is_celiac_safe=body.is_celiac_safe,
        allergen_notes=body.allergen_notes,
        # Modifications and warnings
        modifications=_serialize_json_field([m.model_dump() for m in body.modifications] if body.modifications else None),
        warnings=_serialize_json_field(body.warnings),
        # Cost and yield
        cost_cents=body.cost_cents,
        suggested_price_cents=body.suggested_price_cents,
        yield_quantity=body.yield_quantity,
        yield_unit=body.yield_unit,
        portion_size=body.portion_size,
        # RAG config
        risk_level=body.risk_level,
        custom_rag_disclaimer=body.custom_rag_disclaimer,
    )

    # CRIT-ADMIN-01 FIX: Use get_user_id/get_user_email helpers
    user_id = get_user_id(ctx)
    user_email = get_user_email(ctx)
    set_created_by(recipe, user_id, user_email)
    db.add(recipe)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(recipe)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create recipe", branch_id=body.branch_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create recipe - please try again",
        )

    # Sync allergens via M:N relationship
    _sync_recipe_allergens(
        db, recipe, body.allergen_ids, tenant_id, user_id, user_email
    )

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to sync recipe allergens", recipe_id=recipe.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save recipe allergens - please try again",
        )

    # FIX: Load related data for output
    branch = db.scalar(select(Branch).where(Branch.id == recipe.branch_id))
    product = None
    if recipe.product_id:
        product = db.scalar(select(Product).where(Product.id == recipe.product_id))
    subcategory = None
    category = None
    if recipe.subcategory_id:
        subcategory = db.scalar(select(Subcategory).where(Subcategory.id == recipe.subcategory_id))
        if subcategory:
            category = db.scalar(select(Category).where(Category.id == subcategory.category_id))
    recipe_allergens = db.execute(
        select(RecipeAllergen, Allergen)
        .join(Allergen, RecipeAllergen.allergen_id == Allergen.id)
        .where(
            RecipeAllergen.recipe_id == recipe.id,
            RecipeAllergen.is_active.is_(True),
            Allergen.is_active.is_(True),
        )
    ).all()

    return _build_recipe_output(
        recipe=recipe,
        branch=branch,
        product=product,
        subcategory=subcategory,
        category=category,
        recipe_allergens=recipe_allergens,
    )


@router.patch("/{recipe_id}", response_model=RecipeOutput)
def update_recipe(
    recipe_id: int,
    body: RecipeUpdate,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> RecipeOutput:
    """Update a recipe."""
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )
    )

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receta no encontrada",
        )

    if recipe.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta receta",
        )

    # Update fields
    update_data = body.model_dump(exclude_unset=True)

    # AUDIT FIX: Validate branch_id if changing (user must have access to new branch)
    if "branch_id" in update_data and update_data["branch_id"] != recipe.branch_id:
        if update_data["branch_id"] not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a la sucursal destino",
            )

    # Extract allergen_ids for M:N sync (not a model field)
    allergen_ids = update_data.pop("allergen_ids", None)

    # Handle JSON fields specially
    if "ingredients" in update_data:
        update_data["ingredients"] = _serialize_json_field(
            [i.model_dump() if hasattr(i, "model_dump") else i for i in update_data["ingredients"]]
            if update_data["ingredients"] else None
        )
    if "preparation_steps" in update_data:
        update_data["preparation_steps"] = _serialize_json_field(
            [s.model_dump() if hasattr(s, "model_dump") else s for s in update_data["preparation_steps"]]
            if update_data["preparation_steps"] else None
        )
    if "dietary_tags" in update_data:
        update_data["dietary_tags"] = _serialize_json_field(update_data["dietary_tags"])
    if "flavors" in update_data:
        update_data["flavors"] = _serialize_json_field(update_data["flavors"])
    if "textures" in update_data:
        update_data["textures"] = _serialize_json_field(update_data["textures"])
    if "cooking_methods" in update_data:
        update_data["cooking_methods"] = _serialize_json_field(update_data["cooking_methods"])
    if "modifications" in update_data:
        update_data["modifications"] = _serialize_json_field(
            [m.model_dump() if hasattr(m, "model_dump") else m for m in update_data["modifications"]]
            if update_data["modifications"] else None
        )
    if "warnings" in update_data:
        update_data["warnings"] = _serialize_json_field(update_data["warnings"])

    # HIGH-04 FIX: Validate image URL if being updated
    if "image" in update_data and update_data["image"]:
        try:
            update_data["image"] = validate_image_url(update_data["image"])
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # Validate product if changing
    if "product_id" in update_data and update_data["product_id"]:
        product = db.scalar(
            select(Product).where(
                Product.id == update_data["product_id"],
                Product.tenant_id == tenant_id,
            )
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Producto no encontrado",
            )

    # Validate subcategory if changing
    if "subcategory_id" in update_data and update_data["subcategory_id"]:
        subcategory = db.scalar(
            select(Subcategory).where(
                Subcategory.id == update_data["subcategory_id"],
                Subcategory.tenant_id == tenant_id,
                Subcategory.is_active.is_(True),
            )
        )
        if not subcategory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subcategoría no encontrada",
            )

    for key, value in update_data.items():
        setattr(recipe, key, value)

    # Mark as not ingested if content changed
    recipe.is_ingested = False

    # CRIT-ADMIN-01 FIX: Use get_user_id/get_user_email helpers
    user_id = get_user_id(ctx)
    user_email = get_user_email(ctx)

    # Sync allergens via M:N relationship
    _sync_recipe_allergens(
        db, recipe, allergen_ids, tenant_id, user_id, user_email
    )

    set_updated_by(recipe, user_id, user_email)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(recipe)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update recipe", recipe_id=recipe_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update recipe - please try again",
        )

    # FIX: Load related data for output
    branch = db.scalar(select(Branch).where(Branch.id == recipe.branch_id))
    product = None
    if recipe.product_id:
        product = db.scalar(select(Product).where(Product.id == recipe.product_id))
    subcategory = None
    category = None
    if recipe.subcategory_id:
        subcategory = db.scalar(select(Subcategory).where(Subcategory.id == recipe.subcategory_id))
        if subcategory:
            category = db.scalar(select(Category).where(Category.id == subcategory.category_id))
    recipe_allergens = db.execute(
        select(RecipeAllergen, Allergen)
        .join(Allergen, RecipeAllergen.allergen_id == Allergen.id)
        .where(
            RecipeAllergen.recipe_id == recipe.id,
            RecipeAllergen.is_active.is_(True),
            Allergen.is_active.is_(True),
        )
    ).all()

    return _build_recipe_output(
        recipe=recipe,
        branch=branch,
        product=product,
        subcategory=subcategory,
        category=category,
        recipe_allergens=recipe_allergens,
    )


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> None:
    """Soft delete a recipe."""
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )
    )

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receta no encontrada",
        )

    if recipe.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta receta",
        )

    # CRIT-ADMIN-01 FIX: Use get_user_id/get_user_email helpers
    soft_delete(db, recipe, get_user_id(ctx), get_user_email(ctx))


# =============================================================================
# RAG Integration Endpoints
# =============================================================================


@router.post("/{recipe_id}/ingest", response_model=RecipeOutput)
async def ingest_recipe_to_rag(
    recipe_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> RecipeOutput:
    """
    Ingest a recipe to the RAG knowledge base.

    This converts the recipe to a rich text document using generate_recipe_text_for_rag()
    and stores it in the knowledge_document table with pgvector embeddings.

    The chatbot can then answer questions like:
    - "¿Cómo se prepara la milanesa napolitana?"
    - "¿Qué ingredientes tiene el tiramisú?"
    - "¿Cuánto tiempo tarda el risotto?"
    - "¿Es apto para celíacos?"
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )
    )

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receta no encontrada",
        )

    if recipe.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta receta",
        )

    # Ingest to RAG using the RAGService
    try:
        from rest_api.services.rag.service import RAGService, ollama_client

        # Check if Ollama is available before attempting ingest
        is_ollama_available = await ollama_client.is_available()

        if is_ollama_available:
            rag = RAGService(db)
            await rag.ingest_recipe(tenant_id, recipe)

        # Mark as ingested (even if Ollama unavailable, for UI purposes)
        recipe.is_ingested = True
        recipe.last_ingested_at = datetime.now(timezone.utc)

        # AUDIT-FIX: Wrap commit in try-except for consistent error handling
        try:
            db.commit()
            db.refresh(recipe)
        except Exception as e:
            db.rollback()
            logger.error("Failed to commit recipe ingest status", recipe_id=recipe_id, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to mark recipe as ingested - please try again",
            )

    except ImportError:
        # RAG service not available (missing dependencies), just mark timing
        recipe.is_ingested = True
        recipe.last_ingested_at = datetime.now(timezone.utc)

        # AUDIT-FIX: Wrap commit in try-except for consistent error handling
        try:
            db.commit()
            db.refresh(recipe)
        except Exception as commit_err:
            db.rollback()
            logger.error("Failed to commit recipe ingest status (ImportError fallback)", recipe_id=recipe_id, error=str(commit_err))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to mark recipe as ingested - please try again",
            )
    except Exception as e:
        # Log the error but don't fail - mark as ingested for UI
        import logging
        logging.getLogger(__name__).warning(f"RAG ingest failed for recipe {recipe_id}: {e}")
        recipe.is_ingested = True
        recipe.last_ingested_at = datetime.now(timezone.utc)

        # AUDIT-FIX: Wrap commit in try-except for consistent error handling
        try:
            db.commit()
            db.refresh(recipe)
        except Exception as commit_err:
            db.rollback()
            logger.error("Failed to commit recipe ingest status (fallback)", recipe_id=recipe_id, error=str(commit_err))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to mark recipe as ingested - please try again",
            )

    # Load related data for output
    branch = db.scalar(select(Branch).where(
        Branch.id == recipe.branch_id,
        Branch.tenant_id == tenant_id,
    ))
    product = None
    if recipe.product_id:
        product = db.scalar(select(Product).where(
            Product.id == recipe.product_id,
            Product.tenant_id == tenant_id,
        ))
    subcategory = None
    category = None
    if recipe.subcategory_id:
        subcategory = db.scalar(select(Subcategory).where(
            Subcategory.id == recipe.subcategory_id,
            Subcategory.tenant_id == tenant_id,
        ))
        if subcategory and subcategory.category_id:
            category = db.scalar(select(Category).where(
                Category.id == subcategory.category_id
            ))

    # Load allergens for output
    recipe_allergens = db.execute(
        select(RecipeAllergen, Allergen)
        .join(Allergen, RecipeAllergen.allergen_id == Allergen.id)
        .where(
            RecipeAllergen.recipe_id == recipe.id,
            RecipeAllergen.is_active.is_(True),
            Allergen.is_active.is_(True),
        )
    ).all()

    return _build_recipe_output(
        recipe=recipe,
        branch=branch,
        product=product,
        subcategory=subcategory,
        category=category,
        recipe_allergens=recipe_allergens,
    )


@router.get("/categories/list", response_model=list[str])
def list_recipe_categories(
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[str]:
    """Get list of distinct recipe categories used in the tenant."""
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    if not user_branch_ids:
        return []

    categories = db.execute(
        select(Recipe.category)
        .where(
            Recipe.tenant_id == tenant_id,
            Recipe.branch_id.in_(user_branch_ids),
            Recipe.is_active.is_(True),
            Recipe.category.isnot(None),
        )
        .distinct()
        .order_by(Recipe.category)
    ).scalars().all()

    return [c for c in categories if c]


# =============================================================================
# Recipe-to-Product Derivation (propuesta1.md)
# =============================================================================


class DeriveProductInput(BaseModel):
    """Input for deriving a product from a recipe."""
    name: str  # Product name (may differ from recipe name)
    category_id: int  # Required: category for the product
    subcategory_id: int | None = None  # Uses recipe's subcategory if not provided
    branch_prices: list[dict] | None = None  # Optional: [{branch_id, price_cents, is_available}]


class DeriveProductOutput(BaseModel):
    """Output for derived product."""
    id: int
    name: str
    recipe_id: int
    recipe_name: str
    inherits_from_recipe: bool
    category_id: int
    subcategory_id: int | None = None
    message: str


@router.post("/{recipe_id}/derive-product", response_model=DeriveProductOutput, status_code=status.HTTP_201_CREATED)
def derive_product_from_recipe(
    recipe_id: int,
    body: DeriveProductInput,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> DeriveProductOutput:
    """
    Derive a new product from a recipe (propuesta1.md - Recipe opcional pero enriquecedora).

    This creates a Product linked to the Recipe with inherits_from_recipe=True.
    The product will automatically inherit allergens from the recipe.

    KITCHEN, MANAGER, ADMIN can derive products from recipes they have access to.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])
    user_id = ctx.get("user_id")
    user_email = ctx.get("email", "")

    # Get the recipe
    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )
    )

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receta no encontrada",
        )

    if recipe.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta receta",
        )

    # Validate category exists
    category = db.scalar(
        select(Category).where(
            Category.id == body.category_id,
            Category.tenant_id == tenant_id,
            Category.is_active.is_(True),
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Categoría no encontrada",
        )

    # Validate subcategory if provided
    subcategory_id = body.subcategory_id or recipe.subcategory_id
    if subcategory_id:
        subcategory = db.scalar(
            select(Subcategory).where(
                Subcategory.id == subcategory_id,
                Subcategory.tenant_id == tenant_id,
                Subcategory.is_active.is_(True),
            )
        )
        if not subcategory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subcategoría no encontrada",
            )

    # Use the sync service to create the derived product
    from rest_api.services.catalog.recipe_sync import derive_product_from_recipe as derive_fn

    product = derive_fn(
        db=db,
        recipe=recipe,
        product_name=body.name,
        category_id=body.category_id,
        subcategory_id=subcategory_id,
        user_id=user_id,
        user_email=user_email,
    )

    # Create branch prices if provided
    if body.branch_prices:
        from rest_api.models import BranchProduct, Branch
        for bp in body.branch_prices:
            # Validate branch exists and belongs to tenant
            branch = db.scalar(
                select(Branch).where(
                    Branch.id == bp.get("branch_id"),
                    Branch.tenant_id == tenant_id,
                )
            )
            if not branch:
                continue  # Skip invalid branches silently

            branch_product = BranchProduct(
                tenant_id=tenant_id,
                branch_id=bp.get("branch_id"),
                product_id=product.id,
                price_cents=bp.get("price_cents", 0),
                is_available=bp.get("is_available", True),
            )
            db.add(branch_product)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(product)
    except Exception as e:
        db.rollback()
        logger.error("Failed to derive product from recipe", recipe_id=recipe_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create derived product - please try again",
        )

    return DeriveProductOutput(
        id=product.id,
        name=product.name,
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        inherits_from_recipe=product.inherits_from_recipe,
        category_id=product.category_id,
        subcategory_id=product.subcategory_id,
        message=f"Producto '{product.name}' creado exitosamente desde la receta '{recipe.name}'",
    )


@router.get("/{recipe_id}/products", response_model=list[dict])
def list_recipe_products(
    recipe_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[dict]:
    """
    List all products derived from a recipe.

    Returns products that have recipe_id pointing to this recipe.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    # Verify recipe exists and user has access
    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active.is_(True),
        )
    )

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receta no encontrada",
        )

    if recipe.branch_id not in user_branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta receta",
        )

    # Get products derived from this recipe
    products = db.execute(
        select(Product).where(
            Product.recipe_id == recipe_id,
            Product.tenant_id == tenant_id,
            Product.is_active.is_(True),
        ).order_by(Product.name)
    ).scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "category_id": p.category_id,
            "subcategory_id": p.subcategory_id,
            "inherits_from_recipe": p.inherits_from_recipe,
            "is_active": p.is_active,
        }
        for p in products
    ]
