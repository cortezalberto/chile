"""
Product Service - Clean Architecture Implementation.

CLEAN-ARCH: Handles all product-related business logic including:
- Basic product CRUD
- Branch pricing (BranchProduct)
- Allergen management (ProductAllergen)
- Canonical model: ingredients, dietary, cooking, sensory profiles
- Modifications, warnings, RAG config
- Recipe synchronization

Usage:
    from rest_api.services.domain import ProductService

    service = ProductService(db)
    products = service.list_by_branch(tenant_id, branch_id)
    product = service.create(data, tenant_id, user_id, user_email)
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload, joinedload

from rest_api.models import (
    Product, BranchProduct, Category, Subcategory, Branch,
    Allergen, ProductAllergen, Ingredient, ProductIngredient,
    ProductDietaryProfile, CookingMethod, ProductCookingMethod,
    ProductCooking, FlavorProfile, TextureProfile,
    ProductFlavor, ProductTexture, ProductModification,
    ProductWarning, ProductRAGConfig, Recipe,
)
from shared.utils.admin_schemas import (
    ProductOutput, BranchPriceOutput, AllergenPresenceOutput,
)
from rest_api.services.base_service import BaseCRUDService
from rest_api.services.crud.soft_delete import soft_delete, set_created_by, set_updated_by
from rest_api.services.events import publish_entity_deleted
from shared.utils.exceptions import ValidationError, NotFoundError
from shared.utils.validators import validate_image_url
from shared.config.constants import (
    AllergenPresence, RiskLevel, WarningSeverity, ModificationAction,
)
from shared.config.logging import get_logger

logger = get_logger(__name__)


class ProductService(BaseCRUDService[Product, ProductOutput]):
    """
    Service for product management.

    Business rules:
    - Products belong to a category (and optional subcategory)
    - Products have per-branch pricing via BranchProduct
    - Products can have allergens with presence types
    - Products can link to recipes and inherit allergens
    - Soft delete preserves audit trail
    """

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Product,
            output_schema=ProductOutput,
            entity_name="Producto",
            has_branch_id=False,  # Products are not directly branch-scoped
        )

    # =========================================================================
    # Query Methods
    # =========================================================================

    def list_with_relations(
        self,
        tenant_id: int,
        *,
        category_id: int | None = None,
        branch_id: int | None = None,
        branch_ids: list[int] | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductOutput]:
        """
        List products with all relations eagerly loaded.

        Args:
            tenant_id: Tenant ID for isolation.
            category_id: Optional category filter.
            branch_id: Optional single branch filter.
            branch_ids: Optional list of branches (for MANAGER access).
            include_inactive: Include soft-deleted products.
            limit: Maximum results (capped at 500).
            offset: Skip count.

        Returns:
            List of ProductOutput DTOs.
        """
        limit = min(max(1, limit), 500)
        offset = max(0, offset)

        query = (
            select(Product)
            .options(
                selectinload(Product.branch_products),
                selectinload(Product.product_allergens).joinedload(ProductAllergen.allergen),
                joinedload(Product.recipe),
            )
            .where(Product.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.where(Product.is_active.is_(True))

        if category_id:
            query = query.where(Product.category_id == category_id)

        # Apply branch filter
        if branch_ids:
            query = query.join(BranchProduct).where(BranchProduct.branch_id.in_(branch_ids))
        elif branch_id:
            query = query.join(BranchProduct).where(BranchProduct.branch_id == branch_id)

        query = query.order_by(Product.name).offset(offset).limit(limit)
        products = self._db.execute(query).scalars().unique().all()

        return [self.to_output(p) for p in products]

    def get_with_relations(
        self,
        product_id: int,
        tenant_id: int,
    ) -> ProductOutput:
        """Get a single product with all relations."""
        product = self._db.scalar(
            select(Product)
            .options(
                selectinload(Product.branch_products),
                selectinload(Product.product_allergens).joinedload(ProductAllergen.allergen),
                joinedload(Product.recipe),
            )
            .where(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
        )

        if not product:
            raise NotFoundError(self._entity_name, product_id, tenant_id=tenant_id)

        return self.to_output(product)

    def get_product_branch_ids(self, product: Product) -> list[int]:
        """Get list of branch IDs where product is available."""
        return [bp.branch_id for bp in product.branch_products]

    # =========================================================================
    # Create Operations
    # =========================================================================

    def create_full(
        self,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> ProductOutput:
        """
        Create product with all related entities.

        Handles: branch_prices, allergens, ingredients, dietary_profile,
        cooking_info, sensory_profile, modifications, warnings, rag_config.
        """
        # Extract related data
        branch_prices = data.pop("branch_prices", [])
        allergens = data.pop("allergens", [])
        allergen_ids = data.pop("allergen_ids", [])
        ingredients = data.pop("ingredients", [])
        dietary_profile = data.pop("dietary_profile", None)
        cooking_info = data.pop("cooking_info", None)
        sensory_profile = data.pop("sensory_profile", None)
        modifications = data.pop("modifications", [])
        warnings = data.pop("warnings", [])
        rag_config = data.pop("rag_config", None)

        # Validate
        self._validate_create(data, tenant_id)
        self._validate_branch_prices(branch_prices, tenant_id)

        # Validate image URL
        if data.get("image"):
            try:
                data["image"] = validate_image_url(data["image"])
            except ValueError as e:
                raise ValidationError(str(e), field="image")

        # Build allergen_ids for legacy field
        allergen_ids_legacy = []
        if allergens:
            allergen_ids_legacy = [
                a["allergen_id"] if isinstance(a, dict) else a.allergen_id
                for a in allergens
                if (a.get("presence_type") if isinstance(a, dict) else a.presence_type) == AllergenPresence.CONTAINS
            ]
        elif allergen_ids:
            allergen_ids_legacy = allergen_ids

        # Create product
        data["tenant_id"] = tenant_id
        data["allergen_ids"] = json.dumps(allergen_ids_legacy) if allergen_ids_legacy else None

        product = Product(**data)
        set_created_by(product, user_id, user_email)
        self._db.add(product)
        self._db.flush()

        # Create related entities
        self._create_allergens(product, allergens, allergen_ids, tenant_id, user_id, user_email)
        self._create_branch_prices(product, branch_prices, tenant_id)
        self._create_ingredients(product, ingredients, tenant_id, user_id, user_email)
        self._create_dietary_profile(product, dietary_profile, user_id, user_email)
        self._create_cooking_info(product, cooking_info, user_id, user_email)
        self._create_sensory_profile(product, sensory_profile)
        self._create_modifications(product, modifications, tenant_id, user_id, user_email)
        self._create_warnings(product, warnings, tenant_id, user_id, user_email)
        self._create_rag_config(product, rag_config, user_id, user_email)

        # Sync from recipe if needed
        if product.inherits_from_recipe and product.recipe_id:
            self._sync_from_recipe(product, user_id, user_email)

        self._db.commit()
        self._db.refresh(product)

        return self.to_output(product)

    # =========================================================================
    # Update Operations
    # =========================================================================

    def update_full(
        self,
        product_id: int,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> ProductOutput:
        """Update product with all related entities."""
        product = self._get_product_for_update(product_id, tenant_id)

        # Extract related data
        branch_prices = data.pop("branch_prices", None)
        allergens = data.pop("allergens", None)
        allergen_ids = data.pop("allergen_ids", None)
        ingredients = data.pop("ingredients", None)
        dietary_profile = data.pop("dietary_profile", None)
        cooking_info = data.pop("cooking_info", None)
        sensory_profile = data.pop("sensory_profile", None)
        modifications = data.pop("modifications", None)
        warnings_data = data.pop("warnings", None)
        rag_config = data.pop("rag_config", None)

        # Validate image URL if being updated
        if "image" in data and data["image"]:
            try:
                data["image"] = validate_image_url(data["image"])
            except ValueError as e:
                raise ValidationError(str(e), field="image")

        # Validate recipe if changing
        recipe_id = data.get("recipe_id")
        if recipe_id is not None and recipe_id:
            self._validate_recipe(recipe_id, tenant_id)

        # Update basic fields
        for key, value in data.items():
            if hasattr(product, key):
                setattr(product, key, value)

        set_updated_by(product, user_id, user_email)

        # Update related entities (if provided)
        if allergens is not None or allergen_ids is not None:
            self._update_allergens(product, allergens, allergen_ids, tenant_id, user_id, user_email)

        if branch_prices is not None:
            self._validate_branch_prices(branch_prices, tenant_id)
            self._update_branch_prices(product, branch_prices, tenant_id)

        if ingredients is not None:
            self._update_ingredients(product, ingredients, tenant_id, user_id, user_email)

        if dietary_profile is not None:
            self._update_dietary_profile(product, dietary_profile, user_id, user_email)

        if cooking_info is not None:
            self._update_cooking_info(product, cooking_info, user_id, user_email)

        if sensory_profile is not None:
            self._update_sensory_profile(product, sensory_profile)

        if modifications is not None:
            self._update_modifications(product, modifications, tenant_id, user_id, user_email)

        if warnings_data is not None:
            self._update_warnings(product, warnings_data, tenant_id, user_id, user_email)

        if rag_config is not None:
            self._update_rag_config(product, rag_config, user_id, user_email)

        # Sync from recipe if needed
        if product.inherits_from_recipe and product.recipe_id:
            self._sync_from_recipe(product, user_id, user_email)

        self._db.commit()
        self._db.refresh(product)

        return self.to_output(product)

    # =========================================================================
    # Delete Operations
    # =========================================================================

    def delete_product(
        self,
        product_id: int,
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Soft delete a product."""
        product = self._get_product_for_update(product_id, tenant_id)

        category = self._db.scalar(
            select(Category).where(Category.id == product.category_id)
        )
        branch_id = category.branch_id if category else None

        product_name = product.name

        soft_delete(self._db, product, user_id, user_email)

        publish_entity_deleted(
            tenant_id=tenant_id,
            entity_type="product",
            entity_id=product_id,
            entity_name=product_name,
            branch_id=branch_id,
            actor_user_id=user_id,
        )

    # =========================================================================
    # Transformation
    # =========================================================================

    def to_output(self, product: Product) -> ProductOutput:
        """Convert product entity to output DTO."""
        # Build branch prices
        branch_prices = [
            BranchPriceOutput(
                branch_id=bp.branch_id,
                price_cents=bp.price_cents,
                is_available=bp.is_available,
            )
            for bp in (product.branch_products or [])
        ]

        # Parse allergen_ids (old format)
        allergen_ids = []
        if product.allergen_ids:
            try:
                allergen_ids = json.loads(product.allergen_ids)
            except (json.JSONDecodeError, TypeError):
                pass

        # Build allergens list (new format)
        allergens = []
        if hasattr(product, "product_allergens") and product.product_allergens:
            for pa in product.product_allergens:
                if pa.allergen and pa.allergen.is_active:
                    allergens.append(AllergenPresenceOutput(
                        allergen_id=pa.allergen_id,
                        allergen_name=pa.allergen.name,
                        allergen_icon=pa.allergen.icon,
                        presence_type=pa.presence_type,
                    ))

        # Get recipe name
        recipe_name = None
        if product.recipe_id and hasattr(product, "recipe") and product.recipe:
            recipe_name = product.recipe.name

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

    # =========================================================================
    # Validation
    # =========================================================================

    def _validate_create(self, data: dict[str, Any], tenant_id: int) -> None:
        """Validate product creation data."""
        category_id = data.get("category_id")
        if not category_id:
            raise ValidationError("category_id es requerido", field="category_id")

        category = self._db.scalar(
            select(Category).where(
                Category.id == category_id,
                Category.tenant_id == tenant_id,
            )
        )
        if not category:
            raise ValidationError("category_id inválido", field="category_id")

        # Validate subcategory if provided
        subcategory_id = data.get("subcategory_id")
        if subcategory_id:
            subcategory = self._db.scalar(
                select(Subcategory).where(
                    Subcategory.id == subcategory_id,
                    Subcategory.tenant_id == tenant_id,
                )
            )
            if not subcategory:
                raise ValidationError("subcategory_id inválido", field="subcategory_id")

        # Validate recipe if provided
        recipe_id = data.get("recipe_id")
        if recipe_id:
            self._validate_recipe(recipe_id, tenant_id)

    def _validate_recipe(self, recipe_id: int, tenant_id: int) -> None:
        """Validate recipe exists and belongs to tenant."""
        recipe = self._db.scalar(
            select(Recipe).where(
                Recipe.id == recipe_id,
                Recipe.tenant_id == tenant_id,
                Recipe.is_active.is_(True),
            )
        )
        if not recipe:
            raise ValidationError("recipe_id inválido", field="recipe_id")

    def _validate_branch_prices(
        self, branch_prices: list[dict | Any], tenant_id: int
    ) -> None:
        """Validate branch prices."""
        for bp in branch_prices:
            branch_id = bp.get("branch_id") if isinstance(bp, dict) else bp.branch_id
            branch = self._db.scalar(
                select(Branch).where(
                    Branch.id == branch_id,
                    Branch.tenant_id == tenant_id,
                )
            )
            if not branch:
                raise ValidationError(f"branch_id inválido: {branch_id}", field="branch_prices")

    def _validate_allergen(self, allergen_id: int, tenant_id: int) -> Allergen:
        """Validate allergen exists and return it."""
        allergen = self._db.scalar(
            select(Allergen).where(
                Allergen.id == allergen_id,
                Allergen.tenant_id == tenant_id,
                Allergen.is_active.is_(True),
            )
        )
        if not allergen:
            raise ValidationError(f"allergen_id inválido: {allergen_id}", field="allergens")
        return allergen

    def _validate_presence_type(self, presence_type: str) -> None:
        """Validate allergen presence type."""
        if presence_type not in AllergenPresence.ALL:
            raise ValidationError(
                f"presence_type inválido: {presence_type}",
                field="presence_type",
            )

    # =========================================================================
    # Private Helpers - Create
    # =========================================================================

    def _get_product_for_update(self, product_id: int, tenant_id: int) -> Product:
        """Get product with relations for update."""
        product = self._db.scalar(
            select(Product)
            .options(selectinload(Product.branch_products))
            .where(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
        )
        if not product:
            raise NotFoundError(self._entity_name, product_id, tenant_id=tenant_id)
        return product

    def _create_allergens(
        self,
        product: Product,
        allergens: list[dict | Any],
        allergen_ids: list[int],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductAllergen records."""
        if allergens:
            for allergen_input in allergens:
                allergen_id = allergen_input.get("allergen_id") if isinstance(allergen_input, dict) else allergen_input.allergen_id
                presence_type = allergen_input.get("presence_type", AllergenPresence.CONTAINS) if isinstance(allergen_input, dict) else allergen_input.presence_type

                self._validate_allergen(allergen_id, tenant_id)
                self._validate_presence_type(presence_type)

                pa = ProductAllergen(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    allergen_id=allergen_id,
                    presence_type=presence_type,
                )
                set_created_by(pa, user_id, user_email)
                self._db.add(pa)
        elif allergen_ids:
            for allergen_id in allergen_ids:
                self._validate_allergen(allergen_id, tenant_id)
                pa = ProductAllergen(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    allergen_id=allergen_id,
                    presence_type=AllergenPresence.CONTAINS,
                )
                set_created_by(pa, user_id, user_email)
                self._db.add(pa)

    def _create_branch_prices(
        self,
        product: Product,
        branch_prices: list[dict | Any],
        tenant_id: int,
    ) -> None:
        """Create BranchProduct records."""
        for bp in branch_prices:
            branch_id = bp.get("branch_id") if isinstance(bp, dict) else bp.branch_id
            price_cents = bp.get("price_cents") if isinstance(bp, dict) else bp.price_cents
            is_available = bp.get("is_available", True) if isinstance(bp, dict) else bp.is_available

            branch_product = BranchProduct(
                tenant_id=tenant_id,
                branch_id=branch_id,
                product_id=product.id,
                price_cents=price_cents,
                is_available=is_available,
            )
            self._db.add(branch_product)

    def _create_ingredients(
        self,
        product: Product,
        ingredients: list[dict | Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductIngredient records."""
        for ing in ingredients:
            ing_id = ing.get("ingredient_id") if isinstance(ing, dict) else ing.ingredient_id
            is_main = ing.get("is_main", False) if isinstance(ing, dict) else ing.is_main
            notes = ing.get("notes") if isinstance(ing, dict) else ing.notes

            ingredient = self._db.scalar(
                select(Ingredient).where(
                    Ingredient.id == ing_id,
                    Ingredient.tenant_id == tenant_id,
                    Ingredient.is_active.is_(True),
                )
            )
            if not ingredient:
                raise ValidationError(f"ingredient_id inválido: {ing_id}", field="ingredients")

            pi = ProductIngredient(
                tenant_id=tenant_id,
                product_id=product.id,
                ingredient_id=ing_id,
                is_main=is_main,
                notes=notes,
            )
            set_created_by(pi, user_id, user_email)
            self._db.add(pi)

    def _create_dietary_profile(
        self,
        product: Product,
        profile: dict | Any | None,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductDietaryProfile."""
        if not profile:
            return

        dietary = ProductDietaryProfile(
            product_id=product.id,
            is_vegetarian=self._get_field(profile, "is_vegetarian", False),
            is_vegan=self._get_field(profile, "is_vegan", False),
            is_gluten_free=self._get_field(profile, "is_gluten_free", False),
            is_dairy_free=self._get_field(profile, "is_dairy_free", False),
            is_celiac_safe=self._get_field(profile, "is_celiac_safe", False),
            is_keto=self._get_field(profile, "is_keto", False),
            is_low_sodium=self._get_field(profile, "is_low_sodium", False),
        )
        set_created_by(dietary, user_id, user_email)
        self._db.add(dietary)

    def _create_cooking_info(
        self,
        product: Product,
        info: dict | Any | None,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductCookingMethod and ProductCooking records."""
        if not info:
            return

        method_ids = self._get_field(info, "cooking_method_ids", [])
        for method_id in method_ids:
            method = self._db.scalar(
                select(CookingMethod).where(
                    CookingMethod.id == method_id,
                    CookingMethod.is_active.is_(True),
                )
            )
            if not method:
                raise ValidationError(f"cooking_method_id inválido: {method_id}", field="cooking_info")
            self._db.add(ProductCookingMethod(product_id=product.id, cooking_method_id=method_id))

        cooking = ProductCooking(
            product_id=product.id,
            uses_oil=self._get_field(info, "uses_oil", False),
            prep_time_minutes=self._get_field(info, "prep_time_minutes"),
            cook_time_minutes=self._get_field(info, "cook_time_minutes"),
        )
        set_created_by(cooking, user_id, user_email)
        self._db.add(cooking)

    def _create_sensory_profile(
        self,
        product: Product,
        profile: dict | Any | None,
    ) -> None:
        """Create ProductFlavor and ProductTexture records."""
        if not profile:
            return

        flavor_ids = self._get_field(profile, "flavor_ids", [])
        for flavor_id in flavor_ids:
            flavor = self._db.scalar(
                select(FlavorProfile).where(
                    FlavorProfile.id == flavor_id,
                    FlavorProfile.is_active.is_(True),
                )
            )
            if not flavor:
                raise ValidationError(f"flavor_profile_id inválido: {flavor_id}", field="sensory_profile")
            self._db.add(ProductFlavor(product_id=product.id, flavor_profile_id=flavor_id))

        texture_ids = self._get_field(profile, "texture_ids", [])
        for texture_id in texture_ids:
            texture = self._db.scalar(
                select(TextureProfile).where(
                    TextureProfile.id == texture_id,
                    TextureProfile.is_active.is_(True),
                )
            )
            if not texture:
                raise ValidationError(f"texture_profile_id inválido: {texture_id}", field="sensory_profile")
            self._db.add(ProductTexture(product_id=product.id, texture_profile_id=texture_id))

    def _create_modifications(
        self,
        product: Product,
        modifications: list[dict | Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductModification records."""
        for mod in modifications:
            action = self._get_field(mod, "action")
            if action not in ModificationAction.ALL:
                raise ValidationError(f"action inválida: {action}", field="modifications")

            modification = ProductModification(
                tenant_id=tenant_id,
                product_id=product.id,
                action=action,
                item=self._get_field(mod, "item"),
                is_allowed=self._get_field(mod, "is_allowed", True),
                extra_cost_cents=self._get_field(mod, "extra_cost_cents", 0),
            )
            set_created_by(modification, user_id, user_email)
            self._db.add(modification)

    def _create_warnings(
        self,
        product: Product,
        warnings: list[dict | Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductWarning records."""
        for warn in warnings:
            severity = self._get_field(warn, "severity", WarningSeverity.INFO)
            if severity not in WarningSeverity.ALL:
                raise ValidationError(f"severity inválida: {severity}", field="warnings")

            warning = ProductWarning(
                tenant_id=tenant_id,
                product_id=product.id,
                text=self._get_field(warn, "text"),
                severity=severity,
            )
            set_created_by(warning, user_id, user_email)
            self._db.add(warning)

    def _create_rag_config(
        self,
        product: Product,
        config: dict | Any | None,
        user_id: int,
        user_email: str,
    ) -> None:
        """Create ProductRAGConfig."""
        if not config:
            return

        risk_level = self._get_field(config, "risk_level", RiskLevel.LOW)
        if risk_level not in RiskLevel.ALL:
            raise ValidationError(f"risk_level inválido: {risk_level}", field="rag_config")

        rag_config = ProductRAGConfig(
            product_id=product.id,
            risk_level=risk_level,
            custom_disclaimer=self._get_field(config, "custom_disclaimer"),
            highlight_allergens=self._get_field(config, "highlight_allergens", True),
        )
        set_created_by(rag_config, user_id, user_email)
        self._db.add(rag_config)

    # =========================================================================
    # Private Helpers - Update
    # =========================================================================

    def _update_allergens(
        self,
        product: Product,
        allergens: list[dict | Any] | None,
        allergen_ids: list[int] | None,
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update ProductAllergen records."""
        # Clear existing
        self._db.execute(
            ProductAllergen.__table__.delete().where(ProductAllergen.product_id == product.id)
        )

        # Convert allergen_ids to allergens format if provided
        if allergens is None and allergen_ids is not None:
            allergens = [{"allergen_id": aid, "presence_type": AllergenPresence.CONTAINS} for aid in allergen_ids]

        if not allergens:
            product.allergen_ids = None
            return

        allergen_ids_legacy = []
        for allergen_input in allergens:
            allergen_id = self._get_field(allergen_input, "allergen_id")
            presence_type = self._get_field(allergen_input, "presence_type", AllergenPresence.CONTAINS)

            self._validate_allergen(allergen_id, tenant_id)
            self._validate_presence_type(presence_type)

            pa = ProductAllergen(
                tenant_id=tenant_id,
                product_id=product.id,
                allergen_id=allergen_id,
                presence_type=presence_type,
            )
            set_created_by(pa, user_id, user_email)
            self._db.add(pa)

            if presence_type == AllergenPresence.CONTAINS:
                allergen_ids_legacy.append(allergen_id)

        product.allergen_ids = json.dumps(allergen_ids_legacy) if allergen_ids_legacy else None

    def _update_branch_prices(
        self,
        product: Product,
        branch_prices: list[dict | Any],
        tenant_id: int,
    ) -> None:
        """Update BranchProduct records."""
        self._db.execute(
            BranchProduct.__table__.delete().where(BranchProduct.product_id == product.id)
        )
        self._create_branch_prices(product, branch_prices, tenant_id)

    def _update_ingredients(
        self,
        product: Product,
        ingredients: list[dict | Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update ProductIngredient records."""
        self._db.execute(
            ProductIngredient.__table__.delete().where(ProductIngredient.product_id == product.id)
        )
        self._create_ingredients(product, ingredients, tenant_id, user_id, user_email)

    def _update_dietary_profile(
        self,
        product: Product,
        profile: dict | Any,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update ProductDietaryProfile."""
        self._db.execute(
            ProductDietaryProfile.__table__.delete().where(ProductDietaryProfile.product_id == product.id)
        )
        self._create_dietary_profile(product, profile, user_id, user_email)

    def _update_cooking_info(
        self,
        product: Product,
        info: dict | Any,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update cooking information."""
        self._db.execute(
            ProductCookingMethod.__table__.delete().where(ProductCookingMethod.product_id == product.id)
        )
        self._db.execute(
            ProductCooking.__table__.delete().where(ProductCooking.product_id == product.id)
        )
        self._create_cooking_info(product, info, user_id, user_email)

    def _update_sensory_profile(
        self,
        product: Product,
        profile: dict | Any,
    ) -> None:
        """Update sensory profile."""
        self._db.execute(
            ProductFlavor.__table__.delete().where(ProductFlavor.product_id == product.id)
        )
        self._db.execute(
            ProductTexture.__table__.delete().where(ProductTexture.product_id == product.id)
        )
        self._create_sensory_profile(product, profile)

    def _update_modifications(
        self,
        product: Product,
        modifications: list[dict | Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update modifications."""
        self._db.execute(
            ProductModification.__table__.delete().where(ProductModification.product_id == product.id)
        )
        self._create_modifications(product, modifications, tenant_id, user_id, user_email)

    def _update_warnings(
        self,
        product: Product,
        warnings: list[dict | Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update warnings."""
        self._db.execute(
            ProductWarning.__table__.delete().where(ProductWarning.product_id == product.id)
        )
        self._create_warnings(product, warnings, tenant_id, user_id, user_email)

    def _update_rag_config(
        self,
        product: Product,
        config: dict | Any,
        user_id: int,
        user_email: str,
    ) -> None:
        """Update RAG config."""
        self._db.execute(
            ProductRAGConfig.__table__.delete().where(ProductRAGConfig.product_id == product.id)
        )
        self._create_rag_config(product, config, user_id, user_email)

    def _sync_from_recipe(
        self,
        product: Product,
        user_id: int,
        user_email: str,
    ) -> None:
        """Sync allergens from linked recipe."""
        from rest_api.services.catalog.recipe_sync import sync_product_from_recipe
        sync_product_from_recipe(self._db, product, user_id, user_email)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def _get_field(obj: dict | Any, field: str, default: Any = None) -> Any:
        """Get field from dict or object."""
        if isinstance(obj, dict):
            return obj.get(field, default)
        return getattr(obj, field, default)
