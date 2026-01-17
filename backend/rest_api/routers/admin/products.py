"""
Product management endpoints with canonical model support (Phases 0-4).
"""

import json
from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    selectinload, joinedload,
    get_db, current_user,
    Product, BranchProduct, Category, Subcategory, Branch,
    Allergen, ProductAllergen,
    Ingredient, ProductIngredient, ProductDietaryProfile,
    CookingMethod, FlavorProfile, TextureProfile,
    ProductCookingMethod, ProductFlavor, ProductTexture,
    ProductCooking, ProductModification, ProductWarning, ProductRAGConfig,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin,
)
from rest_api.routers.admin_schemas import (
    ProductOutput, ProductCreate, ProductUpdate,
    BranchPriceOutput, AllergenPresenceOutput,
)


router = APIRouter(tags=["admin-products"])


def _build_product_output(product: Product, db: Session = None, preloaded_branch_products: list = None) -> ProductOutput:
    """Build ProductOutput with branch prices and allergens.

    Args:
        product: The Product model instance
        db: Database session (only needed if branch_products not preloaded)
        preloaded_branch_products: Pre-fetched BranchProduct list (avoids N+1)
    """
    # Use preloaded branch_products if available, otherwise query (for single product fetch)
    if preloaded_branch_products is not None:
        branch_products = preloaded_branch_products
    elif hasattr(product, 'branch_products') and product.branch_products is not None:
        # Access eager-loaded relationship
        branch_products = product.branch_products
    elif db is not None:
        # Fallback to query (for backwards compatibility)
        branch_products = db.execute(
            select(BranchProduct).where(BranchProduct.product_id == product.id)
        ).scalars().all()
    else:
        branch_products = []

    branch_prices = [
        BranchPriceOutput(
            branch_id=bp.branch_id,
            price_cents=bp.price_cents,
            is_available=bp.is_available,
        )
        for bp in branch_products
    ]

    # Parse allergen_ids (old format - backward compatible)
    allergen_ids = []
    if product.allergen_ids:
        try:
            allergen_ids = json.loads(product.allergen_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    # Build allergens list from ProductAllergen relationship (new format - Phase 0)
    allergens = []
    if hasattr(product, 'product_allergens') and product.product_allergens:
        for pa in product.product_allergens:
            if pa.allergen and pa.allergen.is_active:
                allergens.append(AllergenPresenceOutput(
                    allergen_id=pa.allergen_id,
                    allergen_name=pa.allergen.name,
                    allergen_icon=pa.allergen.icon,
                    presence_type=pa.presence_type,
                ))
    elif db is not None:
        # Fallback: query ProductAllergen with allergen details
        product_allergens = db.execute(
            select(ProductAllergen)
            .options(joinedload(ProductAllergen.allergen))
            .where(
                ProductAllergen.product_id == product.id,
                ProductAllergen.is_active == True,
            )
        ).scalars().unique().all()
        for pa in product_allergens:
            if pa.allergen and pa.allergen.is_active:
                allergens.append(AllergenPresenceOutput(
                    allergen_id=pa.allergen_id,
                    allergen_name=pa.allergen.name,
                    allergen_icon=pa.allergen.icon,
                    presence_type=pa.presence_type,
                ))

    # Get recipe name if linked (propuesta1.md)
    recipe_name = None
    if product.recipe_id:
        if hasattr(product, 'recipe') and product.recipe:
            recipe_name = product.recipe.name
        elif db is not None:
            from rest_api.models import Recipe
            recipe = db.scalar(select(Recipe).where(Recipe.id == product.recipe_id))
            recipe_name = recipe.name if recipe else None

    return ProductOutput(
        id=product.id,
        tenant_id=product.tenant_id,
        name=product.name,
        description=product.description,
        image=product.image,
        category_id=product.category_id,
        subcategory_id=product.subcategory_id,
        featured=product.featured,
        popular=product.popular,
        badge=product.badge,
        seal=product.seal,
        allergen_ids=allergen_ids,
        allergens=allergens,
        recipe_id=product.recipe_id,
        inherits_from_recipe=product.inherits_from_recipe,
        recipe_name=recipe_name,
        is_active=product.is_active,
        created_at=product.created_at,
        branch_prices=branch_prices,
    )


@router.get("/products", response_model=list[ProductOutput])
def list_products(
    category_id: int | None = None,
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[ProductOutput]:
    """List products, optionally filtered by category or branch."""
    # Eager load branch_products, product_allergens, and recipe to avoid N+1 queries
    query = select(Product).options(
        selectinload(Product.branch_products),
        selectinload(Product.product_allergens).joinedload(ProductAllergen.allergen),
        joinedload(Product.recipe),
    ).where(Product.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Product.is_active == True)

    if category_id:
        query = query.where(Product.category_id == category_id)

    if branch_id:
        # Filter to products available in this branch
        query = query.join(BranchProduct).where(BranchProduct.branch_id == branch_id)

    products = db.execute(query.order_by(Product.name)).scalars().unique().all()
    return [_build_product_output(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductOutput)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """Get a specific product with branch prices and allergens."""
    product = db.scalar(
        select(Product).options(
            selectinload(Product.branch_products),
            selectinload(Product.product_allergens).joinedload(ProductAllergen.allergen),
            joinedload(Product.recipe),
        ).where(
            Product.id == product_id,
            Product.tenant_id == user["tenant_id"],
            Product.is_active == True,
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return _build_product_output(product)


@router.post("/products", response_model=ProductOutput, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """Create a new product with branch prices and allergens."""
    # Verify category belongs to tenant
    category = db.scalar(
        select(Category).where(
            Category.id == body.category_id,
            Category.tenant_id == user["tenant_id"],
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category_id",
        )

    # Verify subcategory if provided
    if body.subcategory_id:
        subcategory = db.scalar(
            select(Subcategory).where(
                Subcategory.id == body.subcategory_id,
                Subcategory.tenant_id == user["tenant_id"],
            )
        )
        if not subcategory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid subcategory_id",
            )

    # Determine which allergen format is being used
    allergen_ids_for_legacy = []
    if body.allergens:
        allergen_ids_for_legacy = [a.allergen_id for a in body.allergens if a.presence_type == "contains"]
    elif body.allergen_ids:
        allergen_ids_for_legacy = body.allergen_ids

    # Validate recipe_id if provided (propuesta1.md)
    if body.recipe_id:
        from rest_api.models import Recipe
        recipe = db.scalar(
            select(Recipe).where(
                Recipe.id == body.recipe_id,
                Recipe.tenant_id == user["tenant_id"],
                Recipe.is_active == True,
            )
        )
        if not recipe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recipe_id",
            )

    product = Product(
        tenant_id=user["tenant_id"],
        name=body.name,
        description=body.description,
        image=body.image,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        featured=body.featured,
        popular=body.popular,
        badge=body.badge,
        seal=body.seal,
        allergen_ids=json.dumps(allergen_ids_for_legacy) if allergen_ids_for_legacy else None,
        is_active=body.is_active,
        recipe_id=body.recipe_id,
        inherits_from_recipe=body.inherits_from_recipe,
    )
    set_created_by(product, get_user_id(user), get_user_email(user))
    db.add(product)
    db.flush()

    # Create ProductAllergen records (Phase 0)
    if body.allergens:
        for allergen_input in body.allergens:
            allergen = db.scalar(
                select(Allergen).where(
                    Allergen.id == allergen_input.allergen_id,
                    Allergen.tenant_id == user["tenant_id"],
                    Allergen.is_active == True,
                )
            )
            if not allergen:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid allergen_id: {allergen_input.allergen_id}",
                )
            if allergen_input.presence_type not in ("contains", "may_contain", "free_from"):
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid presence_type: {allergen_input.presence_type}",
                )
            product_allergen = ProductAllergen(
                tenant_id=user["tenant_id"],
                product_id=product.id,
                allergen_id=allergen_input.allergen_id,
                presence_type=allergen_input.presence_type,
            )
            set_created_by(product_allergen, get_user_id(user), get_user_email(user))
            db.add(product_allergen)
    elif body.allergen_ids:
        for allergen_id in body.allergen_ids:
            allergen = db.scalar(
                select(Allergen).where(
                    Allergen.id == allergen_id,
                    Allergen.tenant_id == user["tenant_id"],
                    Allergen.is_active == True,
                )
            )
            if not allergen:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid allergen_id: {allergen_id}",
                )
            product_allergen = ProductAllergen(
                tenant_id=user["tenant_id"],
                product_id=product.id,
                allergen_id=allergen_id,
                presence_type="contains",
            )
            set_created_by(product_allergen, get_user_id(user), get_user_email(user))
            db.add(product_allergen)

    # Create branch prices
    for bp in body.branch_prices:
        branch = db.scalar(
            select(Branch).where(
                Branch.id == bp.branch_id,
                Branch.tenant_id == user["tenant_id"],
            )
        )
        if not branch:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch_id: {bp.branch_id}",
            )
        branch_product = BranchProduct(
            tenant_id=user["tenant_id"],
            branch_id=bp.branch_id,
            product_id=product.id,
            price_cents=bp.price_cents,
            is_available=bp.is_available,
        )
        db.add(branch_product)

    # Sync allergens from recipe if inherits_from_recipe is True
    if body.inherits_from_recipe and body.recipe_id:
        from rest_api.services.recipe_product_sync import sync_product_from_recipe
        sync_product_from_recipe(db, product, get_user_id(user), get_user_email(user))

    # Phase 1: Ingredients
    if body.ingredients:
        for ing_input in body.ingredients:
            ingredient = db.scalar(
                select(Ingredient).where(
                    Ingredient.id == ing_input.ingredient_id,
                    Ingredient.tenant_id == user["tenant_id"],
                    Ingredient.is_active == True,
                )
            )
            if not ingredient:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid ingredient_id: {ing_input.ingredient_id}",
                )
            product_ingredient = ProductIngredient(
                tenant_id=user["tenant_id"],
                product_id=product.id,
                ingredient_id=ing_input.ingredient_id,
                is_main=ing_input.is_main,
                notes=ing_input.notes,
            )
            set_created_by(product_ingredient, get_user_id(user), get_user_email(user))
            db.add(product_ingredient)

    # Phase 2: Dietary Profile
    if body.dietary_profile:
        dietary = ProductDietaryProfile(
            product_id=product.id,
            is_vegetarian=body.dietary_profile.is_vegetarian,
            is_vegan=body.dietary_profile.is_vegan,
            is_gluten_free=body.dietary_profile.is_gluten_free,
            is_dairy_free=body.dietary_profile.is_dairy_free,
            is_celiac_safe=body.dietary_profile.is_celiac_safe,
            is_keto=body.dietary_profile.is_keto,
            is_low_sodium=body.dietary_profile.is_low_sodium,
        )
        set_created_by(dietary, get_user_id(user), get_user_email(user))
        db.add(dietary)

    # Phase 3: Cooking Information
    if body.cooking_info:
        for method_id in body.cooking_info.cooking_method_ids:
            method = db.scalar(
                select(CookingMethod).where(
                    CookingMethod.id == method_id,
                    CookingMethod.is_active == True,
                )
            )
            if not method:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid cooking_method_id: {method_id}",
                )
            db.add(ProductCookingMethod(product_id=product.id, cooking_method_id=method_id))

        cooking = ProductCooking(
            product_id=product.id,
            uses_oil=body.cooking_info.uses_oil,
            prep_time_minutes=body.cooking_info.prep_time_minutes,
            cook_time_minutes=body.cooking_info.cook_time_minutes,
        )
        set_created_by(cooking, get_user_id(user), get_user_email(user))
        db.add(cooking)

    # Phase 3: Sensory Profile
    if body.sensory_profile:
        for flavor_id in body.sensory_profile.flavor_ids:
            flavor = db.scalar(
                select(FlavorProfile).where(
                    FlavorProfile.id == flavor_id,
                    FlavorProfile.is_active == True,
                )
            )
            if not flavor:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid flavor_profile_id: {flavor_id}",
                )
            db.add(ProductFlavor(product_id=product.id, flavor_profile_id=flavor_id))

        for texture_id in body.sensory_profile.texture_ids:
            texture = db.scalar(
                select(TextureProfile).where(
                    TextureProfile.id == texture_id,
                    TextureProfile.is_active == True,
                )
            )
            if not texture:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid texture_profile_id: {texture_id}",
                )
            db.add(ProductTexture(product_id=product.id, texture_profile_id=texture_id))

    # Phase 4: Modifications
    for mod_input in body.modifications:
        if mod_input.action not in ("remove", "substitute"):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid modification action: {mod_input.action}",
            )
        modification = ProductModification(
            tenant_id=user["tenant_id"],
            product_id=product.id,
            action=mod_input.action,
            item=mod_input.item,
            is_allowed=mod_input.is_allowed,
            extra_cost_cents=mod_input.extra_cost_cents,
        )
        set_created_by(modification, get_user_id(user), get_user_email(user))
        db.add(modification)

    # Phase 4: Warnings
    for warn_input in body.warnings:
        if warn_input.severity not in ("info", "warning", "danger"):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid warning severity: {warn_input.severity}",
            )
        warning = ProductWarning(
            tenant_id=user["tenant_id"],
            product_id=product.id,
            text=warn_input.text,
            severity=warn_input.severity,
        )
        set_created_by(warning, get_user_id(user), get_user_email(user))
        db.add(warning)

    # Phase 4: RAG Configuration
    if body.rag_config:
        if body.rag_config.risk_level not in ("low", "medium", "high"):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid risk_level: {body.rag_config.risk_level}",
            )
        rag_config = ProductRAGConfig(
            product_id=product.id,
            risk_level=body.rag_config.risk_level,
            custom_disclaimer=body.rag_config.custom_disclaimer,
            highlight_allergens=body.rag_config.highlight_allergens,
        )
        set_created_by(rag_config, get_user_id(user), get_user_email(user))
        db.add(rag_config)

    db.commit()
    db.refresh(product)
    return _build_product_output(product, db)


@router.patch("/products/{product_id}", response_model=ProductOutput)
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """Update a product and its branch prices and allergens."""
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == user["tenant_id"],
            Product.is_active == True,
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Handle recipe linkage
    recipe_id = update_data.pop("recipe_id", None)
    inherits_from_recipe = update_data.pop("inherits_from_recipe", None)

    if recipe_id is not None:
        if recipe_id:
            from rest_api.models import Recipe
            recipe = db.scalar(
                select(Recipe).where(
                    Recipe.id == recipe_id,
                    Recipe.tenant_id == user["tenant_id"],
                    Recipe.is_active == True,
                )
            )
            if not recipe:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid recipe_id",
                )
        product.recipe_id = recipe_id if recipe_id else None

    if inherits_from_recipe is not None:
        product.inherits_from_recipe = inherits_from_recipe

    # Handle allergens (new format)
    allergens = update_data.pop("allergens", None)

    # Handle allergen_ids (old format)
    if "allergen_ids" in update_data:
        allergen_ids = update_data.pop("allergen_ids")
        if allergens is None and allergen_ids is not None:
            allergens = [{"allergen_id": aid, "presence_type": "contains"} for aid in allergen_ids]
        update_data["allergen_ids"] = json.dumps(allergen_ids) if allergen_ids else None

    # Handle branch_prices separately
    branch_prices = update_data.pop("branch_prices", None)

    # Handle canonical model fields separately
    ingredients = update_data.pop("ingredients", None)
    dietary_profile = update_data.pop("dietary_profile", None)
    cooking_info = update_data.pop("cooking_info", None)
    sensory_profile = update_data.pop("sensory_profile", None)
    modifications = update_data.pop("modifications", None)
    warnings = update_data.pop("warnings", None)
    rag_config = update_data.pop("rag_config", None)

    for key, value in update_data.items():
        setattr(product, key, value)

    set_updated_by(product, get_user_id(user), get_user_email(user))

    # Update allergens if provided
    if allergens is not None:
        db.execute(
            ProductAllergen.__table__.delete().where(ProductAllergen.product_id == product_id)
        )
        allergen_ids_for_legacy = []
        for allergen_input in allergens:
            allergen_id = allergen_input.get("allergen_id") if isinstance(allergen_input, dict) else allergen_input.allergen_id
            presence_type = allergen_input.get("presence_type", "contains") if isinstance(allergen_input, dict) else allergen_input.presence_type

            allergen = db.scalar(
                select(Allergen).where(
                    Allergen.id == allergen_id,
                    Allergen.tenant_id == user["tenant_id"],
                    Allergen.is_active == True,
                )
            )
            if not allergen:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid allergen_id: {allergen_id}",
                )
            if presence_type not in ("contains", "may_contain", "free_from"):
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid presence_type: {presence_type}",
                )
            product_allergen = ProductAllergen(
                tenant_id=user["tenant_id"],
                product_id=product_id,
                allergen_id=allergen_id,
                presence_type=presence_type,
            )
            set_created_by(product_allergen, get_user_id(user), get_user_email(user))
            db.add(product_allergen)

            if presence_type == "contains":
                allergen_ids_for_legacy.append(allergen_id)

        product.allergen_ids = json.dumps(allergen_ids_for_legacy) if allergen_ids_for_legacy else None

    # Update branch prices if provided
    if branch_prices is not None:
        for bp in branch_prices:
            branch = db.scalar(
                select(Branch).where(
                    Branch.id == bp.branch_id,
                    Branch.tenant_id == user["tenant_id"],
                    Branch.is_active == True,
                )
            )
            if not branch:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid branch_id: {bp.branch_id}",
                )

        db.execute(
            BranchProduct.__table__.delete().where(BranchProduct.product_id == product_id)
        )

        for bp in branch_prices:
            branch_product = BranchProduct(
                tenant_id=user["tenant_id"],
                branch_id=bp.branch_id,
                product_id=product_id,
                price_cents=bp.price_cents,
                is_available=bp.is_available,
            )
            db.add(branch_product)

    # Sync allergens from recipe if needed
    if product.inherits_from_recipe and product.recipe_id:
        from rest_api.services.recipe_product_sync import sync_product_from_recipe
        sync_product_from_recipe(db, product, get_user_id(user), get_user_email(user))

    # Phase 1: Ingredients
    if ingredients is not None:
        db.execute(
            ProductIngredient.__table__.delete().where(ProductIngredient.product_id == product_id)
        )
        for ing_input in ingredients:
            ing_id = ing_input.get("ingredient_id") if isinstance(ing_input, dict) else ing_input.ingredient_id
            is_main = ing_input.get("is_main", False) if isinstance(ing_input, dict) else ing_input.is_main
            notes = ing_input.get("notes") if isinstance(ing_input, dict) else ing_input.notes

            ingredient = db.scalar(
                select(Ingredient).where(
                    Ingredient.id == ing_id,
                    Ingredient.tenant_id == user["tenant_id"],
                    Ingredient.is_active == True,
                )
            )
            if not ingredient:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid ingredient_id: {ing_id}",
                )
            product_ingredient = ProductIngredient(
                tenant_id=user["tenant_id"],
                product_id=product_id,
                ingredient_id=ing_id,
                is_main=is_main,
                notes=notes,
            )
            set_created_by(product_ingredient, get_user_id(user), get_user_email(user))
            db.add(product_ingredient)

    # Phase 2: Dietary Profile
    if dietary_profile is not None:
        db.execute(
            ProductDietaryProfile.__table__.delete().where(ProductDietaryProfile.product_id == product_id)
        )
        if isinstance(dietary_profile, dict):
            dietary = ProductDietaryProfile(
                product_id=product_id,
                is_vegetarian=dietary_profile.get("is_vegetarian", False),
                is_vegan=dietary_profile.get("is_vegan", False),
                is_gluten_free=dietary_profile.get("is_gluten_free", False),
                is_dairy_free=dietary_profile.get("is_dairy_free", False),
                is_celiac_safe=dietary_profile.get("is_celiac_safe", False),
                is_keto=dietary_profile.get("is_keto", False),
                is_low_sodium=dietary_profile.get("is_low_sodium", False),
            )
        else:
            dietary = ProductDietaryProfile(
                product_id=product_id,
                is_vegetarian=dietary_profile.is_vegetarian,
                is_vegan=dietary_profile.is_vegan,
                is_gluten_free=dietary_profile.is_gluten_free,
                is_dairy_free=dietary_profile.is_dairy_free,
                is_celiac_safe=dietary_profile.is_celiac_safe,
                is_keto=dietary_profile.is_keto,
                is_low_sodium=dietary_profile.is_low_sodium,
            )
        set_created_by(dietary, get_user_id(user), get_user_email(user))
        db.add(dietary)

    # Phase 3: Cooking Information
    if cooking_info is not None:
        db.execute(
            ProductCookingMethod.__table__.delete().where(ProductCookingMethod.product_id == product_id)
        )
        db.execute(
            ProductCooking.__table__.delete().where(ProductCooking.product_id == product_id)
        )

        method_ids = cooking_info.get("cooking_method_ids", []) if isinstance(cooking_info, dict) else cooking_info.cooking_method_ids
        uses_oil = cooking_info.get("uses_oil", False) if isinstance(cooking_info, dict) else cooking_info.uses_oil
        prep_time = cooking_info.get("prep_time_minutes") if isinstance(cooking_info, dict) else cooking_info.prep_time_minutes
        cook_time = cooking_info.get("cook_time_minutes") if isinstance(cooking_info, dict) else cooking_info.cook_time_minutes

        for method_id in method_ids:
            method = db.scalar(
                select(CookingMethod).where(
                    CookingMethod.id == method_id,
                    CookingMethod.is_active == True,
                )
            )
            if not method:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid cooking_method_id: {method_id}",
                )
            db.add(ProductCookingMethod(product_id=product_id, cooking_method_id=method_id))

        cooking = ProductCooking(
            product_id=product_id,
            uses_oil=uses_oil,
            prep_time_minutes=prep_time,
            cook_time_minutes=cook_time,
        )
        set_created_by(cooking, get_user_id(user), get_user_email(user))
        db.add(cooking)

    # Phase 3: Sensory Profile
    if sensory_profile is not None:
        db.execute(
            ProductFlavor.__table__.delete().where(ProductFlavor.product_id == product_id)
        )
        db.execute(
            ProductTexture.__table__.delete().where(ProductTexture.product_id == product_id)
        )

        flavor_ids = sensory_profile.get("flavor_ids", []) if isinstance(sensory_profile, dict) else sensory_profile.flavor_ids
        texture_ids = sensory_profile.get("texture_ids", []) if isinstance(sensory_profile, dict) else sensory_profile.texture_ids

        for flavor_id in flavor_ids:
            flavor = db.scalar(
                select(FlavorProfile).where(
                    FlavorProfile.id == flavor_id,
                    FlavorProfile.is_active == True,
                )
            )
            if not flavor:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid flavor_profile_id: {flavor_id}",
                )
            db.add(ProductFlavor(product_id=product_id, flavor_profile_id=flavor_id))

        for texture_id in texture_ids:
            texture = db.scalar(
                select(TextureProfile).where(
                    TextureProfile.id == texture_id,
                    TextureProfile.is_active == True,
                )
            )
            if not texture:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid texture_profile_id: {texture_id}",
                )
            db.add(ProductTexture(product_id=product_id, texture_profile_id=texture_id))

    # Phase 4: Modifications
    if modifications is not None:
        db.execute(
            ProductModification.__table__.delete().where(ProductModification.product_id == product_id)
        )
        for mod in modifications:
            action = mod.get("action") if isinstance(mod, dict) else mod.action
            item = mod.get("item") if isinstance(mod, dict) else mod.item
            is_allowed = mod.get("is_allowed", True) if isinstance(mod, dict) else mod.is_allowed
            extra_cost = mod.get("extra_cost_cents", 0) if isinstance(mod, dict) else mod.extra_cost_cents

            if action not in ("remove", "substitute"):
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid modification action: {action}",
                )
            modification = ProductModification(
                tenant_id=user["tenant_id"],
                product_id=product_id,
                action=action,
                item=item,
                is_allowed=is_allowed,
                extra_cost_cents=extra_cost,
            )
            set_created_by(modification, get_user_id(user), get_user_email(user))
            db.add(modification)

    # Phase 4: Warnings
    if warnings is not None:
        db.execute(
            ProductWarning.__table__.delete().where(ProductWarning.product_id == product_id)
        )
        for warn in warnings:
            text = warn.get("text") if isinstance(warn, dict) else warn.text
            severity = warn.get("severity", "info") if isinstance(warn, dict) else warn.severity

            if severity not in ("info", "warning", "danger"):
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid warning severity: {severity}",
                )
            warning = ProductWarning(
                tenant_id=user["tenant_id"],
                product_id=product_id,
                text=text,
                severity=severity,
            )
            set_created_by(warning, get_user_id(user), get_user_email(user))
            db.add(warning)

    # Phase 4: RAG Configuration
    if rag_config is not None:
        db.execute(
            ProductRAGConfig.__table__.delete().where(ProductRAGConfig.product_id == product_id)
        )
        risk_level = rag_config.get("risk_level", "low") if isinstance(rag_config, dict) else rag_config.risk_level
        custom_disclaimer = rag_config.get("custom_disclaimer") if isinstance(rag_config, dict) else rag_config.custom_disclaimer
        highlight_allergens = rag_config.get("highlight_allergens", True) if isinstance(rag_config, dict) else rag_config.highlight_allergens

        if risk_level not in ("low", "medium", "high"):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid risk_level: {risk_level}",
            )
        new_rag_config = ProductRAGConfig(
            product_id=product_id,
            risk_level=risk_level,
            custom_disclaimer=custom_disclaimer,
            highlight_allergens=highlight_allergens,
        )
        set_created_by(new_rag_config, get_user_id(user), get_user_email(user))
        db.add(new_rag_config)

    db.commit()
    db.refresh(product)
    return _build_product_output(product, db)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a product. Requires ADMIN role."""
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == user["tenant_id"],
            Product.is_active == True,
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    category = db.scalar(
        select(Category).where(Category.id == product.category_id)
    )
    branch_id = category.branch_id if category else None

    product_name = product.name
    tenant_id = product.tenant_id

    soft_delete(db, product, get_user_id(user), get_user_email(user))

    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="product",
        entity_id=product_id,
        entity_name=product_name,
        branch_id=branch_id,
        actor_user_id=get_user_id(user),
    )
