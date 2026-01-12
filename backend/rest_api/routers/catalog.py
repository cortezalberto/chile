"""
Public catalog router.
Exposes menu data for the pwaMenu application.
No authentication required for public endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import (
    Branch,
    Category,
    Subcategory,
    Product,
    BranchProduct,
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
)
from rest_api.services.product_view import get_product_complete


router = APIRouter(prefix="/api/public", tags=["catalog"])


@router.get("/menu/{branch_slug}", response_model=MenuOutput)
def get_menu(branch_slug: str, db: Session = Depends(get_db)) -> MenuOutput:
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

    # Get all categories for this branch with eager loading for subcategories
    # This avoids N+1 for subcategories
    categories = db.execute(
        select(Category)
        .options(
            selectinload(Category.subcategories),
        )
        .where(
            Category.branch_id == branch.id,
            Category.is_active == True,
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
    for product, branch_product in products_result:
        if product.category_id not in products_by_category:
            products_by_category[product.category_id] = []
        products_by_category[product.category_id].append((product, branch_product))

    category_outputs = []

    for category in categories:
        # Filter only active subcategories and sort by order
        subcategory_outputs = [
            SubcategoryOutput(
                id=sub.id,
                name=sub.name,
                image=sub.image,
                order=sub.order,
            )
            for sub in sorted(category.subcategories, key=lambda s: s.order)
            if sub.is_active
        ]

        # Get products for this category from pre-fetched data
        product_outputs = []
        for product, branch_product in products_by_category.get(category.id, []):
            # Parse allergen_ids from JSON string if present
            allergen_ids = []
            if product.allergen_ids:
                try:
                    allergen_ids = json.loads(product.allergen_ids)
                except (json.JSONDecodeError, TypeError):
                    allergen_ids = []

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
