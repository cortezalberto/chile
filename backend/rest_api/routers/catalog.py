"""
Public catalog router.
Exposes menu data for the pwaMenu application.
No authentication required for public endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from rest_api.db import get_db
from shared.rate_limit import limiter
from rest_api.models import (
    Branch,
    Category,
    Subcategory,
    Product,
    BranchProduct,
    Allergen,
    AllergenCrossReaction,
    ProductAllergen,
    ProductDietaryProfile,
    ProductCooking,
    ProductCookingMethod,
    CookingMethod,
    BranchCategoryExclusion,
    BranchSubcategoryExclusion,
)
from shared.schemas import (
    MenuOutput,
    CategoryOutput,
    SubcategoryOutput,
    ProductOutput,
    ProductCompleteOutput,
    AllergensOutput,
    AllergenInfoOutput,
    DietaryProfileOutput,
    IngredientOutput,
    SubIngredientOutput,
    CookingOutput,
    SensoryOutput,
    ModificationOutput,
    WarningOutput,
    AllergenPublicOutput,
    CrossReactionPublicOutput,
    ProductAllergensOutput,
    ProductDietaryOutput,
    ProductCookingOutput,
)
from rest_api.services.product_view import get_product_complete


router = APIRouter(prefix="/api/public", tags=["catalog"])


@router.get("/menu/{branch_slug}", response_model=MenuOutput)
@limiter.limit("100/minute")
def get_menu(request: Request, branch_slug: str, db: Session = Depends(get_db)) -> MenuOutput:
    """
    Get the complete menu for a branch.

    Returns all categories, subcategories, and available products
    with their prices for the specified branch.

    This endpoint is public and does not require authentication.
    """
    # Find branch by slug
    branch = db.scalar(
        select(Branch).where(
            Branch.slug == branch_slug,
            Branch.is_active == True,
        )
    )

    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch '{branch_slug}' not found",
        )

    import json

    # ROUTER-HIGH-05 FIX: Get excluded category IDs for this branch
    excluded_category_ids = set(
        db.execute(
            select(BranchCategoryExclusion.category_id)
            .where(
                BranchCategoryExclusion.branch_id == branch.id,
                BranchCategoryExclusion.is_active == True,
            )
        ).scalars().all()
    )

    # ROUTER-HIGH-05 FIX: Get excluded subcategory IDs for this branch
    excluded_subcategory_ids = set(
        db.execute(
            select(BranchSubcategoryExclusion.subcategory_id)
            .where(
                BranchSubcategoryExclusion.branch_id == branch.id,
                BranchSubcategoryExclusion.is_active == True,
            )
        ).scalars().all()
    )

    # Get all categories for this branch with eager loading for subcategories
    # This avoids N+1 for subcategories
    # ROUTER-HIGH-05 FIX: Exclude categories that are marked as not sold at this branch
    categories = db.execute(
        select(Category)
        .options(
            selectinload(Category.subcategories),
        )
        .where(
            Category.branch_id == branch.id,
            Category.is_active == True,
            Category.id.notin_(excluded_category_ids) if excluded_category_ids else True,
        )
        .order_by(Category.order)
    ).scalars().unique().all()

    # Pre-fetch all products for this branch's categories in a single query
    # This avoids N+1 for products
    category_ids = [cat.id for cat in categories]
    if category_ids:
        products_result = db.execute(
            select(Product, BranchProduct)
            .join(BranchProduct, Product.id == BranchProduct.product_id)
            .where(
                Product.category_id.in_(category_ids),
                Product.is_active == True,
                BranchProduct.branch_id == branch.id,
                BranchProduct.is_available == True,
            )
        ).all()
    else:
        products_result = []

    # Group products by category_id for O(1) lookup
    products_by_category: dict[int, list[tuple]] = {}
    product_ids = []
    for product, branch_product in products_result:
        if product.category_id not in products_by_category:
            products_by_category[product.category_id] = []
        products_by_category[product.category_id].append((product, branch_product))
        product_ids.append(product.id)

    # Pre-fetch canonical model data for all products (producto3.md improvement)
    # This avoids N+1 queries when building product outputs

    # 1. Allergens with presence types
    allergens_by_product: dict[int, dict[str, list]] = {}
    if product_ids:
        allergen_data = db.execute(
            select(ProductAllergen, Allergen)
            .join(Allergen, ProductAllergen.allergen_id == Allergen.id)
            .where(
                ProductAllergen.product_id.in_(product_ids),
                ProductAllergen.is_active == True,
                Allergen.is_active == True,
            )
        ).all()
        for pa, allergen in allergen_data:
            if pa.product_id not in allergens_by_product:
                allergens_by_product[pa.product_id] = {
                    "contains": [],
                    "may_contain": [],
                    "free_from": [],
                }
            allergen_info = AllergenInfoOutput(
                id=allergen.id,
                name=allergen.name,
                icon=allergen.icon,
            )
            presence = pa.presence_type or "contains"
            if presence in allergens_by_product[pa.product_id]:
                allergens_by_product[pa.product_id][presence].append(allergen_info)

    # 2. Dietary profiles
    dietary_by_product: dict[int, ProductDietaryOutput] = {}
    if product_ids:
        dietary_data = db.execute(
            select(ProductDietaryProfile).where(
                ProductDietaryProfile.product_id.in_(product_ids),
                ProductDietaryProfile.is_active == True,
            )
        ).scalars().all()
        for dp in dietary_data:
            dietary_by_product[dp.product_id] = ProductDietaryOutput(
                is_vegetarian=dp.is_vegetarian,
                is_vegan=dp.is_vegan,
                is_gluten_free=dp.is_gluten_free,
                is_dairy_free=dp.is_dairy_free,
                is_celiac_safe=dp.is_celiac_safe,
                is_keto=dp.is_keto,
                is_low_sodium=dp.is_low_sodium,
            )

    # 3. Cooking methods and properties
    cooking_by_product: dict[int, ProductCookingOutput] = {}
    if product_ids:
        # Get ProductCooking (uses_oil, times)
        cooking_data = db.execute(
            select(ProductCooking).where(
                ProductCooking.product_id.in_(product_ids),
                ProductCooking.is_active == True,
            )
        ).scalars().all()
        for pc in cooking_data:
            cooking_by_product[pc.product_id] = ProductCookingOutput(
                methods=[],
                uses_oil=pc.uses_oil,
                prep_time_minutes=pc.prep_time_minutes,
                cook_time_minutes=pc.cook_time_minutes,
            )

        # Get cooking methods (M:N)
        methods_data = db.execute(
            select(ProductCookingMethod, CookingMethod)
            .join(CookingMethod, ProductCookingMethod.cooking_method_id == CookingMethod.id)
            .where(
                ProductCookingMethod.product_id.in_(product_ids),
                CookingMethod.is_active == True,
            )
        ).all()
        for pcm, method in methods_data:
            if pcm.product_id not in cooking_by_product:
                cooking_by_product[pcm.product_id] = ProductCookingOutput(methods=[], uses_oil=False)
            cooking_by_product[pcm.product_id].methods.append(method.name)

    category_outputs = []

    for category in categories:
        # ROUTER-HIGH-05 FIX: Filter only active subcategories that are not excluded for this branch
        subcategory_outputs = [
            SubcategoryOutput(
                id=sub.id,
                name=sub.name,
                image=sub.image,
                order=sub.order,
            )
            for sub in sorted(category.subcategories, key=lambda s: s.order)
            if sub.is_active and sub.id not in excluded_subcategory_ids
        ]

        # Get products for this category from pre-fetched data
        product_outputs = []
        for product, branch_product in products_by_category.get(category.id, []):
            # Parse allergen_ids from JSON string if present (legacy field)
            allergen_ids = []
            if product.allergen_ids:
                try:
                    allergen_ids = json.loads(product.allergen_ids)
                except (json.JSONDecodeError, TypeError):
                    allergen_ids = []

            # Build canonical model outputs
            allergens_output = None
            if product.id in allergens_by_product:
                data = allergens_by_product[product.id]
                allergens_output = ProductAllergensOutput(
                    contains=data["contains"],
                    may_contain=data["may_contain"],
                    free_from=data["free_from"],
                )

            product_outputs.append(
                ProductOutput(
                    id=product.id,
                    name=product.name,
                    description=product.description,
                    price_cents=branch_product.price_cents,
                    image=product.image,
                    category_id=product.category_id,
                    subcategory_id=product.subcategory_id,
                    featured=product.featured,
                    popular=product.popular,
                    badge=product.badge,
                    seal=product.seal,
                    allergen_ids=allergen_ids,
                    is_available=branch_product.is_available,
                    # Canonical model fields (producto3.md)
                    allergens=allergens_output,
                    dietary=dietary_by_product.get(product.id),
                    cooking=cooking_by_product.get(product.id),
                )
            )

        category_outputs.append(
            CategoryOutput(
                id=category.id,
                name=category.name,
                icon=category.icon,
                image=category.image,
                order=category.order,
                subcategories=subcategory_outputs,
                products=product_outputs,
            )
        )

    return MenuOutput(
        branch_id=branch.id,
        branch_name=branch.name,
        branch_slug=branch.slug,
        categories=category_outputs,
    )


@router.get("/menu/{branch_slug}/products/{product_id}", response_model=ProductOutput)
def get_product(
    branch_slug: str,
    product_id: int,
    db: Session = Depends(get_db),
) -> ProductOutput:
    """
    Get details of a specific product.

    Returns product information including allergens and branch-specific pricing.
    """
    # Find branch
    branch = db.scalar(
        select(Branch).where(
            Branch.slug == branch_slug,
            Branch.is_active == True,
        )
    )

    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch '{branch_slug}' not found",
        )

    # Get product with branch pricing
    result = db.execute(
        select(Product, BranchProduct)
        .join(BranchProduct, Product.id == BranchProduct.product_id)
        .where(
            Product.id == product_id,
            Product.is_active == True,
            BranchProduct.branch_id == branch.id,
        )
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found in branch '{branch_slug}'",
        )

    product, branch_product = result

    # Parse allergen_ids
    allergen_ids = []
    if product.allergen_ids:
        try:
            import json
            allergen_ids = json.loads(product.allergen_ids)
        except (json.JSONDecodeError, TypeError):
            allergen_ids = []

    return ProductOutput(
        id=product.id,
        name=product.name,
        description=product.description,
        price_cents=branch_product.price_cents,
        image=product.image,
        category_id=product.category_id,
        subcategory_id=product.subcategory_id,
        featured=product.featured,
        popular=product.popular,
        badge=product.badge,
        seal=product.seal,
        allergen_ids=allergen_ids,
        is_available=branch_product.is_available,
    )


@router.get("/menu/{branch_slug}/products/{product_id}/complete", response_model=ProductCompleteOutput)
def get_product_complete_endpoint(
    branch_slug: str,
    product_id: int,
    db: Session = Depends(get_db),
) -> ProductCompleteOutput:
    """
    Get complete product details including all canonical model data.

    Phase 5 endpoint: Returns allergens (with presence types), dietary profile,
    ingredients (with sub-ingredients), cooking methods, sensory profile,
    modifications, and warnings.

    This endpoint is used by pwaMenu for detailed product information and
    supports advanced filtering by dietary restrictions and allergens.
    """
    # Find branch
    branch = db.scalar(
        select(Branch).where(
            Branch.slug == branch_slug,
            Branch.is_active == True,
        )
    )

    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch '{branch_slug}' not found",
        )

    # Get product with branch pricing
    result = db.execute(
        select(Product, BranchProduct)
        .join(BranchProduct, Product.id == BranchProduct.product_id)
        .where(
            Product.id == product_id,
            Product.is_active == True,
            BranchProduct.branch_id == branch.id,
        )
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found in branch '{branch_slug}'",
        )

    product, branch_product = result

    # Get complete product view using the service
    complete_view = get_product_complete(db, product_id)

    if not complete_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} data not found",
        )

    # Convert view to output schema
    allergens_output = AllergensOutput(
        contains=[AllergenInfoOutput(**a) for a in complete_view["allergens"]["contains"]],
        may_contain=[AllergenInfoOutput(**a) for a in complete_view["allergens"]["may_contain"]],
        free_from=[AllergenInfoOutput(**a) for a in complete_view["allergens"]["free_from"]],
    )

    dietary_output = DietaryProfileOutput(**complete_view["dietary"])

    ingredients_output = [
        IngredientOutput(
            id=ing["id"],
            name=ing["name"],
            group_name=ing["group_name"],
            is_processed=ing["is_processed"],
            is_main=ing["is_main"],
            notes=ing["notes"],
            sub_ingredients=[SubIngredientOutput(**sub) for sub in ing["sub_ingredients"]],
        )
        for ing in complete_view["ingredients"]
    ]

    cooking_output = CookingOutput(**complete_view["cooking"])
    sensory_output = SensoryOutput(**complete_view["sensory"])
    modifications_output = [ModificationOutput(**m) for m in complete_view["modifications"]]
    warnings_output = [WarningOutput(**w) for w in complete_view["warnings"]]

    return ProductCompleteOutput(
        id=product.id,
        name=product.name,
        description=product.description,
        price_cents=branch_product.price_cents,
        image=product.image,
        category_id=product.category_id,
        subcategory_id=product.subcategory_id,
        featured=product.featured,
        popular=product.popular,
        badge=product.badge,
        is_available=branch_product.is_available,
        allergens=allergens_output,
        dietary=dietary_output,
        ingredients=ingredients_output,
        cooking=cooking_output,
        sensory=sensory_output,
        modifications=modifications_output,
        warnings=warnings_output,
    )


@router.get("/menu/{branch_slug}/allergens", response_model=list[AllergenPublicOutput])
def get_allergens_with_cross_reactions(
    branch_slug: str,
    db: Session = Depends(get_db),
) -> list[AllergenPublicOutput]:
    """
    Get all allergens with cross-reaction information for pwaMenu filters.

    Returns allergens available for the tenant of the specified branch,
    including cross-reaction data for advanced allergen filtering
    (e.g., latex-fruit syndrome).

    This endpoint is public and does not require authentication.
    """
    # Find branch to get tenant_id
    branch = db.scalar(
        select(Branch).where(
            Branch.slug == branch_slug,
            Branch.is_active == True,
        )
    )

    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch '{branch_slug}' not found",
        )

    # Get all active allergens for this tenant
    allergens = db.execute(
        select(Allergen).where(
            Allergen.tenant_id == branch.tenant_id,
            Allergen.is_active == True,
        ).order_by(Allergen.is_mandatory.desc(), Allergen.name)
    ).scalars().all()

    # Pre-fetch all cross-reactions for efficiency
    allergen_ids = [a.id for a in allergens]
    cross_reactions_data = db.execute(
        select(AllergenCrossReaction, Allergen)
        .join(Allergen, AllergenCrossReaction.cross_reacts_with_id == Allergen.id)
        .where(
            AllergenCrossReaction.allergen_id.in_(allergen_ids),
            AllergenCrossReaction.is_active == True,
            Allergen.is_active == True,
        )
    ).all()

    # Group cross-reactions by allergen_id
    cross_reactions_by_allergen: dict[int, list[CrossReactionPublicOutput]] = {}
    for cr, target_allergen in cross_reactions_data:
        if cr.allergen_id not in cross_reactions_by_allergen:
            cross_reactions_by_allergen[cr.allergen_id] = []
        cross_reactions_by_allergen[cr.allergen_id].append(
            CrossReactionPublicOutput(
                id=cr.id,
                cross_reacts_with_id=cr.cross_reacts_with_id,
                cross_reacts_with_name=target_allergen.name,
                probability=cr.probability,
                notes=cr.notes,
            )
        )

    # Build output
    result = []
    for allergen in allergens:
        result.append(
            AllergenPublicOutput(
                id=allergen.id,
                name=allergen.name,
                icon=allergen.icon,
                description=allergen.description,
                is_mandatory=allergen.is_mandatory,
                severity=allergen.severity,
                cross_reactions=cross_reactions_by_allergen.get(allergen.id, []),
            )
        )

    return result
