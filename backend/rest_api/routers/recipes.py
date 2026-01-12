"""
Recipes router.
CRUD operations for recipe technical sheets.
Accessible by KITCHEN, MANAGER, and ADMIN roles.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import Recipe, Product, Branch
from shared.auth import current_user_context, require_roles
from rest_api.services.soft_delete_service import (
    soft_delete,
    set_created_by,
    set_updated_by,
)


router = APIRouter(prefix="/api/recipes", tags=["recipes"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class IngredientItem(BaseModel):
    name: str
    quantity: str
    unit: str
    notes: str | None = None


class PreparationStep(BaseModel):
    step: int
    instruction: str
    time_minutes: int | None = None


class RecipeCreate(BaseModel):
    branch_id: int
    name: str
    description: str | None = None
    image: str | None = None
    product_id: int | None = None
    category: str | None = None
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
    allergens: list[str] | None = None
    dietary_tags: list[str] | None = None
    cost_cents: int | None = None


class RecipeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    image: str | None = None
    product_id: int | None = None
    category: str | None = None
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
    allergens: list[str] | None = None
    dietary_tags: list[str] | None = None
    cost_cents: int | None = None


class RecipeOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    branch_name: str | None = None
    name: str
    description: str | None = None
    image: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    category: str | None = None
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
    allergens: list[str] | None = None
    dietary_tags: list[str] | None = None
    cost_cents: int | None = None
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


def _build_recipe_output(recipe: Recipe, db: Session) -> RecipeOutput:
    """Build RecipeOutput from Recipe model."""
    # Get branch name
    branch = db.scalar(select(Branch).where(Branch.id == recipe.branch_id))
    branch_name = branch.name if branch else None

    # Get product name if linked
    product_name = None
    if recipe.product_id:
        product = db.scalar(select(Product).where(Product.id == recipe.product_id))
        product_name = product.name if product else None

    # Parse JSON fields
    ingredients = _parse_json_field(recipe.ingredients, [])
    preparation_steps = _parse_json_field(recipe.preparation_steps, [])
    allergens = _parse_json_field(recipe.allergens, [])
    dietary_tags = _parse_json_field(recipe.dietary_tags, [])

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
        image=recipe.image,
        product_id=recipe.product_id,
        product_name=product_name,
        category=recipe.category,
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
        allergens=allergens,
        dietary_tags=dietary_tags,
        cost_cents=recipe.cost_cents,
        is_active=recipe.is_active,
        is_ingested=recipe.is_ingested,
        last_ingested_at=recipe.last_ingested_at,
        created_at=recipe.created_at,
        created_by_email=recipe.created_by_email,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[RecipeOutput])
def list_recipes(
    branch_id: int | None = None,
    category: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[RecipeOutput]:
    """
    List recipes for the user's branches.

    KITCHEN: Can see recipes from their assigned branches
    MANAGER/ADMIN: Can see recipes from all their branches
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    if not user_branch_ids:
        return []

    query = select(Recipe).where(Recipe.tenant_id == tenant_id)

    if not include_deleted:
        query = query.where(Recipe.is_active == True)

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

    query = query.order_by(Recipe.name.asc())
    recipes = db.execute(query).scalars().all()

    return [_build_recipe_output(r, db) for r in recipes]


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
            Recipe.is_active == True,
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

    return _build_recipe_output(recipe, db)


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

    recipe = Recipe(
        tenant_id=tenant_id,
        branch_id=body.branch_id,
        name=body.name,
        description=body.description,
        image=body.image,
        product_id=body.product_id,
        category=body.category,
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
        allergens=_serialize_json_field(body.allergens),
        dietary_tags=_serialize_json_field(body.dietary_tags),
        cost_cents=body.cost_cents,
    )

    set_created_by(recipe, ctx.get("user_id"), ctx.get("email", ""))
    db.add(recipe)
    db.commit()
    db.refresh(recipe)

    return _build_recipe_output(recipe, db)


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
            Recipe.is_active == True,
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
    if "allergens" in update_data:
        update_data["allergens"] = _serialize_json_field(update_data["allergens"])
    if "dietary_tags" in update_data:
        update_data["dietary_tags"] = _serialize_json_field(update_data["dietary_tags"])

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

    for key, value in update_data.items():
        setattr(recipe, key, value)

    # Mark as not ingested if content changed
    recipe.is_ingested = False

    set_updated_by(recipe, ctx.get("user_id"), ctx.get("email", ""))
    db.commit()
    db.refresh(recipe)

    return _build_recipe_output(recipe, db)


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
            Recipe.is_active == True,
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

    soft_delete(db, recipe, ctx.get("user_id"), ctx.get("email", ""))


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

    This converts the recipe to a document and adds it to the
    chatbot's knowledge base for answering questions about recipes.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    tenant_id = ctx["tenant_id"]
    user_branch_ids = ctx.get("branch_ids", [])

    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.tenant_id == tenant_id,
            Recipe.is_active == True,
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

    # Build document content for RAG
    content_parts = [
        f"# Receta: {recipe.name}",
        "",
    ]

    if recipe.description:
        content_parts.append(f"**Descripcion:** {recipe.description}")
        content_parts.append("")

    if recipe.category:
        content_parts.append(f"**Categoria:** {recipe.category}")
    if recipe.cuisine_type:
        content_parts.append(f"**Tipo de cocina:** {recipe.cuisine_type}")
    if recipe.difficulty:
        content_parts.append(f"**Dificultad:** {recipe.difficulty}")

    if recipe.prep_time_minutes or recipe.cook_time_minutes:
        content_parts.append("")
        content_parts.append("## Tiempos")
        if recipe.prep_time_minutes:
            content_parts.append(f"- Preparacion: {recipe.prep_time_minutes} minutos")
        if recipe.cook_time_minutes:
            content_parts.append(f"- Coccion: {recipe.cook_time_minutes} minutos")
        total = (recipe.prep_time_minutes or 0) + (recipe.cook_time_minutes or 0)
        if total:
            content_parts.append(f"- Total: {total} minutos")

    if recipe.servings:
        content_parts.append(f"**Porciones:** {recipe.servings}")
    if recipe.calories_per_serving:
        content_parts.append(f"**Calorias por porcion:** {recipe.calories_per_serving}")

    ingredients = _parse_json_field(recipe.ingredients, [])
    if ingredients:
        content_parts.append("")
        content_parts.append("## Ingredientes")
        for ing in ingredients:
            line = f"- {ing.get('quantity', '')} {ing.get('unit', '')} de {ing.get('name', '')}"
            if ing.get('notes'):
                line += f" ({ing['notes']})"
            content_parts.append(line)

    steps = _parse_json_field(recipe.preparation_steps, [])
    if steps:
        content_parts.append("")
        content_parts.append("## Preparacion")
        for step in sorted(steps, key=lambda x: x.get('step', 0)):
            line = f"{step.get('step', '')}. {step.get('instruction', '')}"
            if step.get('time_minutes'):
                line += f" ({step['time_minutes']} min)"
            content_parts.append(line)

    if recipe.chef_notes:
        content_parts.append("")
        content_parts.append("## Notas del Chef")
        content_parts.append(recipe.chef_notes)

    if recipe.presentation_tips:
        content_parts.append("")
        content_parts.append("## Tips de Presentacion")
        content_parts.append(recipe.presentation_tips)

    if recipe.storage_instructions:
        content_parts.append("")
        content_parts.append("## Almacenamiento")
        content_parts.append(recipe.storage_instructions)

    allergens = _parse_json_field(recipe.allergens, [])
    if allergens:
        content_parts.append("")
        content_parts.append(f"**Alergenos:** {', '.join(allergens)}")

    tags = _parse_json_field(recipe.dietary_tags, [])
    if tags:
        content_parts.append(f"**Etiquetas dieteticas:** {', '.join(tags)}")

    document_content = "\n".join(content_parts)

    # Try to ingest to RAG
    try:
        from rest_api.services.rag_service import RAGService

        rag = RAGService()
        await rag.ingest_document(
            content=document_content,
            metadata={
                "source": "recipe",
                "recipe_id": recipe.id,
                "recipe_name": recipe.name,
                "branch_id": recipe.branch_id,
                "category": recipe.category,
            },
            document_type="recipe",
        )

        # Mark as ingested
        recipe.is_ingested = True
        recipe.last_ingested_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(recipe)

    except ImportError:
        # RAG service not available, just mark timing
        recipe.is_ingested = True
        recipe.last_ingested_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(recipe)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al ingestar la receta: {str(e)}",
        )

    return _build_recipe_output(recipe, db)


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
            Recipe.is_active == True,
            Recipe.category.isnot(None),
        )
        .distinct()
        .order_by(Recipe.category)
    ).scalars().all()

    return [c for c in categories if c]
