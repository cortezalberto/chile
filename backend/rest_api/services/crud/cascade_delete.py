"""
Cascade Delete Service with Audit Trail.
CRIT-01 FIX: Preserves audit trail when deleting entities with relationships.

Instead of relying on ORM cascade="all, delete-orphan" which hard-deletes
related records, this service soft-deletes the entire tree, preserving
the audit trail for compliance and debugging.

Usage:
    from rest_api.services.crud.cascade_delete import CascadeDeleteService

    service = CascadeDeleteService(db)
    affected = service.soft_delete_product(product, user_id, user_email)
    # Returns count of affected records (product + allergens + ingredients + etc.)
"""

from typing import Any
from sqlalchemy.orm import Session

from shared.config.logging import get_logger
from .soft_delete import soft_delete, set_updated_by

logger = get_logger(__name__)


class CascadeDeleteService:
    """
    Service for cascading soft deletes with audit trail preservation.

    This service ensures that when a parent entity is soft-deleted,
    all related child entities are also soft-deleted (not hard-deleted),
    preserving the complete audit trail.

    Benefits:
    - Audit compliance: All records preserved for auditing
    - Recovery: Can restore entire entity tree
    - History: Can query "what allergens did product X have when deleted"
    """

    def __init__(self, db: Session):
        self._db = db

    def soft_delete_product(
        self,
        product: Any,
        user_id: int,
        user_email: str,
    ) -> int:
        """
        Soft delete product with all related entities.

        Preserves:
        - ProductAllergen records
        - ProductIngredient records
        - BranchProduct records
        - ProductDietaryProfile
        - ProductCookingMethod records

        Args:
            product: Product entity to delete
            user_id: User performing deletion
            user_email: Email for audit trail

        Returns:
            Count of affected records
        """
        affected = 0

        # Soft delete allergen associations
        for pa in getattr(product, "product_allergens", []):
            if pa.is_active:
                soft_delete(self._db, pa, user_id, user_email, commit=False)
                affected += 1

        # Soft delete ingredient associations
        for pi in getattr(product, "product_ingredients", []):
            if pi.is_active:
                soft_delete(self._db, pi, user_id, user_email, commit=False)
                affected += 1

        # Soft delete branch pricing
        for bp in getattr(product, "branch_products", []):
            if bp.is_active:
                soft_delete(self._db, bp, user_id, user_email, commit=False)
                affected += 1

        # Soft delete dietary profile
        profile = getattr(product, "dietary_profile", None)
        if profile and profile.is_active:
            soft_delete(self._db, profile, user_id, user_email, commit=False)
            affected += 1

        # Soft delete cooking methods (M:N)
        for cm in getattr(product, "cooking_methods", []):
            if hasattr(cm, "is_active") and cm.is_active:
                soft_delete(self._db, cm, user_id, user_email, commit=False)
                affected += 1

        # Soft delete modifications
        for mod in getattr(product, "modifications", []):
            if mod.is_active:
                soft_delete(self._db, mod, user_id, user_email, commit=False)
                affected += 1

        # Soft delete warnings
        for warn in getattr(product, "warnings", []):
            if warn.is_active:
                soft_delete(self._db, warn, user_id, user_email, commit=False)
                affected += 1

        # Finally, soft delete the product itself
        soft_delete(self._db, product, user_id, user_email, commit=False)
        affected += 1

        # Commit all changes atomically
        self._db.commit()

        logger.info(
            "Product cascade soft deleted",
            product_id=product.id,
            affected_records=affected,
            user_id=user_id,
        )

        return affected

    def soft_delete_category(
        self,
        category: Any,
        user_id: int,
        user_email: str,
        include_products: bool = False,
    ) -> int:
        """
        Soft delete category with subcategories.

        Args:
            category: Category entity to delete
            user_id: User performing deletion
            user_email: Email for audit trail
            include_products: Also soft-delete products in category

        Returns:
            Count of affected records
        """
        affected = 0

        # Soft delete subcategories first
        for sub in getattr(category, "subcategories", []):
            if sub.is_active:
                if include_products:
                    # Soft delete products in subcategory
                    for product in getattr(sub, "products", []):
                        if product.is_active:
                            affected += self.soft_delete_product(
                                product, user_id, user_email
                            )

                soft_delete(self._db, sub, user_id, user_email, commit=False)
                affected += 1

        # If including products, delete direct products too
        if include_products:
            for product in getattr(category, "products", []):
                if product.is_active:
                    affected += self.soft_delete_product(
                        product, user_id, user_email
                    )

        # Finally, soft delete the category
        soft_delete(self._db, category, user_id, user_email, commit=False)
        affected += 1

        self._db.commit()

        logger.info(
            "Category cascade soft deleted",
            category_id=category.id,
            affected_records=affected,
            include_products=include_products,
            user_id=user_id,
        )

        return affected

    def soft_delete_recipe(
        self,
        recipe: Any,
        user_id: int,
        user_email: str,
    ) -> int:
        """
        Soft delete recipe with allergen associations.

        Args:
            recipe: Recipe entity to delete
            user_id: User performing deletion
            user_email: Email for audit trail

        Returns:
            Count of affected records
        """
        affected = 0

        # Soft delete recipe allergens
        for ra in getattr(recipe, "recipe_allergens", []):
            if ra.is_active:
                soft_delete(self._db, ra, user_id, user_email, commit=False)
                affected += 1

        # Soft delete the recipe
        soft_delete(self._db, recipe, user_id, user_email, commit=False)
        affected += 1

        self._db.commit()

        logger.info(
            "Recipe cascade soft deleted",
            recipe_id=recipe.id,
            affected_records=affected,
            user_id=user_id,
        )

        return affected

    def soft_delete_round(
        self,
        round: Any,
        user_id: int,
        user_email: str,
    ) -> int:
        """
        Soft delete round with items.

        Note: Rounds should rarely be deleted - typically status changes instead.

        Args:
            round: Round entity to delete
            user_id: User performing deletion
            user_email: Email for audit trail

        Returns:
            Count of affected records
        """
        affected = 0

        # Soft delete round items
        for item in getattr(round, "items", []):
            if item.is_active:
                soft_delete(self._db, item, user_id, user_email, commit=False)
                affected += 1

        # Soft delete the round
        soft_delete(self._db, round, user_id, user_email, commit=False)
        affected += 1

        self._db.commit()

        logger.info(
            "Round cascade soft deleted",
            round_id=round.id,
            affected_records=affected,
            user_id=user_id,
        )

        return affected

    def soft_delete_promotion(
        self,
        promotion: Any,
        user_id: int,
        user_email: str,
    ) -> int:
        """
        Soft delete promotion with branch associations and items.

        Args:
            promotion: Promotion entity to delete
            user_id: User performing deletion
            user_email: Email for audit trail

        Returns:
            Count of affected records
        """
        affected = 0

        # Soft delete promotion branches
        for pb in getattr(promotion, "promotion_branches", []):
            if pb.is_active:
                soft_delete(self._db, pb, user_id, user_email, commit=False)
                affected += 1

        # Soft delete promotion items
        for pi in getattr(promotion, "promotion_items", []):
            if pi.is_active:
                soft_delete(self._db, pi, user_id, user_email, commit=False)
                affected += 1

        # Soft delete the promotion
        soft_delete(self._db, promotion, user_id, user_email, commit=False)
        affected += 1

        self._db.commit()

        logger.info(
            "Promotion cascade soft deleted",
            promotion_id=promotion.id,
            affected_records=affected,
            user_id=user_id,
        )

        return affected

    def restore_product(
        self,
        product: Any,
        user_id: int,
        user_email: str,
    ) -> int:
        """
        Restore soft-deleted product with all related entities.

        Args:
            product: Product entity to restore
            user_id: User performing restoration
            user_email: Email for audit trail

        Returns:
            Count of restored records
        """
        from .soft_delete import restore_entity

        restored = 0

        # Restore the product first
        restore_entity(self._db, product, user_id, user_email, commit=False)
        restored += 1

        # Restore allergen associations
        for pa in getattr(product, "product_allergens", []):
            if not pa.is_active and pa.deleted_at is not None:
                restore_entity(self._db, pa, user_id, user_email, commit=False)
                restored += 1

        # Restore ingredient associations
        for pi in getattr(product, "product_ingredients", []):
            if not pi.is_active and pi.deleted_at is not None:
                restore_entity(self._db, pi, user_id, user_email, commit=False)
                restored += 1

        # Restore branch pricing
        for bp in getattr(product, "branch_products", []):
            if not bp.is_active and bp.deleted_at is not None:
                restore_entity(self._db, bp, user_id, user_email, commit=False)
                restored += 1

        # Restore dietary profile
        profile = getattr(product, "dietary_profile", None)
        if profile and not profile.is_active and profile.deleted_at is not None:
            restore_entity(self._db, profile, user_id, user_email, commit=False)
            restored += 1

        self._db.commit()

        logger.info(
            "Product cascade restored",
            product_id=product.id,
            restored_records=restored,
            user_id=user_id,
        )

        return restored


def get_cascade_delete_service(db: Session) -> CascadeDeleteService:
    """Factory function for dependency injection."""
    return CascadeDeleteService(db)
