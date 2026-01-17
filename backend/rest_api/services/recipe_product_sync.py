"""
Recipe-Product Synchronization Service (propuesta1.md)

This service handles the synchronization of data from Recipe to Product
when a product is linked to a recipe and has inherits_from_recipe=True.

Key features:
- Sync allergens: RecipeAllergen → ProductAllergen
- Sync dietary profile (future)
- Create product from recipe (derivation)
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from rest_api.models import (
    Recipe,
    Product,
    ProductAllergen,
    RecipeAllergen,
    Allergen,
    BranchProduct,
)


def sync_product_from_recipe(
    db: Session,
    product: Product,
    user_id: int | None = None,
    user_email: str = "",
) -> None:
    """
    Synchronize data from Recipe to Product if the product inherits from recipe.

    This function:
    1. Checks if product has a linked recipe and inherits_from_recipe=True
    2. Syncs allergens from RecipeAllergen to ProductAllergen
    3. (Future) Syncs dietary profile, ingredients, etc.

    Args:
        db: Database session
        product: The Product instance to sync
        user_id: ID of user performing the sync
        user_email: Email of user performing the sync
    """
    if not product.inherits_from_recipe or not product.recipe_id:
        return

    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == product.recipe_id,
            Recipe.is_active == True,
        )
    )
    if not recipe:
        return

    # Sync allergens: RecipeAllergen → ProductAllergen
    _sync_allergens_from_recipe(db, product, recipe, user_id, user_email)


def _sync_allergens_from_recipe(
    db: Session,
    product: Product,
    recipe: Recipe,
    user_id: int | None,
    user_email: str,
) -> None:
    """
    Synchronize allergens from Recipe to Product.

    Allergens in the recipe are added to the product with presence_type="contains".
    Allergens removed from the recipe are NOT automatically removed from the product
    (they might have been added independently).
    """
    # Get current product allergen IDs
    current_product_allergen_ids = set(
        db.scalars(
            select(ProductAllergen.allergen_id).where(
                ProductAllergen.product_id == product.id,
                ProductAllergen.is_active == True,
            )
        ).all()
    )

    # Get recipe allergen IDs
    recipe_allergen_ids = set(
        db.scalars(
            select(RecipeAllergen.allergen_id).where(
                RecipeAllergen.recipe_id == recipe.id,
                RecipeAllergen.is_active == True,
            )
        ).all()
    )

    # Add allergens from recipe that are not in product
    allergens_to_add = recipe_allergen_ids - current_product_allergen_ids

    for allergen_id in allergens_to_add:
        # Check if soft-deleted ProductAllergen exists
        existing = db.scalar(
            select(ProductAllergen).where(
                ProductAllergen.product_id == product.id,
                ProductAllergen.allergen_id == allergen_id,
                ProductAllergen.is_active == False,
            )
        )
        if existing:
            # Restore soft-deleted record
            existing.restore(user_id or 0, user_email)
        else:
            # Create new ProductAllergen
            pa = ProductAllergen(
                tenant_id=product.tenant_id,
                product_id=product.id,
                allergen_id=allergen_id,
                presence_type="contains",  # From recipe means it contains the allergen
                risk_level="standard",
            )
            pa.set_created_by(user_id or 0, user_email)
            db.add(pa)


def derive_product_from_recipe(
    db: Session,
    recipe: Recipe,
    product_name: str,
    category_id: int,
    subcategory_id: int | None = None,
    user_id: int | None = None,
    user_email: str = "",
) -> Product:
    """
    Create a new Product derived from a Recipe.

    This is the "Recipe First" flow where:
    1. Chef creates a Recipe with full technical details
    2. Admin/Manager derives a Product for sale from that recipe
    3. Product automatically inherits allergens and can sync on updates

    SVC-MED-05 FIX: Added duplicate check to prevent race condition when
    creating multiple products with the same name from the same recipe.

    Args:
        db: Database session
        recipe: The source Recipe
        product_name: Name for the new product (can differ from recipe name)
        category_id: Category ID for the product
        subcategory_id: Optional subcategory ID
        user_id: ID of user creating the product
        user_email: Email of user creating the product

    Returns:
        The newly created Product instance

    Raises:
        ValueError: If a product with the same name already exists for this tenant
    """
    # SVC-MED-05 FIX: Check for duplicate product name before creating
    existing = db.scalar(
        select(Product).where(
            Product.tenant_id == recipe.tenant_id,
            Product.name == product_name,
            Product.is_active == True,
        )
    )
    if existing:
        raise ValueError(f"Product with name '{product_name}' already exists")

    # Create product with recipe link
    product = Product(
        tenant_id=recipe.tenant_id,
        name=product_name,
        description=recipe.description,
        image=recipe.image,
        category_id=category_id,
        subcategory_id=subcategory_id or recipe.subcategory_id,
        recipe_id=recipe.id,
        inherits_from_recipe=True,
        featured=False,
        popular=False,
    )
    product.set_created_by(user_id or 0, user_email)
    db.add(product)
    db.flush()  # Get product ID

    # Sync allergens from recipe
    _sync_allergens_from_recipe(db, product, recipe, user_id, user_email)

    return product


def sync_all_products_for_recipe(
    db: Session,
    recipe: Recipe,
    user_id: int | None = None,
    user_email: str = "",
) -> int:
    """
    Sync all products that inherit from a specific recipe.

    Call this when a recipe is updated to propagate changes to all
    products that have inherits_from_recipe=True.

    Args:
        db: Database session
        recipe: The Recipe that was updated
        user_id: ID of user performing the sync
        user_email: Email of user performing the sync

    Returns:
        Number of products synced
    """
    # Find all products linked to this recipe that inherit from it
    products = db.scalars(
        select(Product).where(
            Product.recipe_id == recipe.id,
            Product.inherits_from_recipe == True,
            Product.is_active == True,
        )
    ).all()

    synced_count = 0
    for product in products:
        _sync_allergens_from_recipe(db, product, recipe, user_id, user_email)
        synced_count += 1

    return synced_count


def get_recipe_product_summary(db: Session, recipe_id: int) -> dict:
    """
    Get a summary of products derived from a recipe.

    Returns:
        Dict with recipe info and list of derived products
    """
    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.is_active == True,
        )
    )
    if not recipe:
        return {"recipe": None, "products": []}

    products = db.scalars(
        select(Product).where(
            Product.recipe_id == recipe_id,
            Product.is_active == True,
        )
    ).all()

    return {
        "recipe": {
            "id": recipe.id,
            "name": recipe.name,
            "branch_id": recipe.branch_id,
        },
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "inherits_from_recipe": p.inherits_from_recipe,
            }
            for p in products
        ],
    }
