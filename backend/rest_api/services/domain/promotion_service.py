"""
Promotion Service - Clean Architecture Implementation.

CLEAN-ARCH: Handles all promotion-related business logic including:
- Promotion CRUD
- Branch associations (PromotionBranch)
- Item associations (PromotionItem)
- Image URL validation

Usage:
    from rest_api.services.domain import PromotionService

    service = PromotionService(db)
    promotions = service.list_all(tenant_id)
    promotion = service.create_full(data, tenant_id, user_id, user_email)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from rest_api.models import Promotion, PromotionBranch, PromotionItem, Branch, Product
from rest_api.services.crud.soft_delete import soft_delete, set_created_by, set_updated_by
from rest_api.services.events import publish_entity_deleted
from shared.utils.validators import validate_image_url
from shared.utils.exceptions import NotFoundError, ValidationError, ForbiddenError
from shared.config.logging import get_logger
from shared.config.constants import Roles

logger = get_logger(__name__)


# =============================================================================
# Output Schema (moved from router for clean architecture)
# =============================================================================


class PromotionItemOutput(BaseModel):
    product_id: int
    quantity: int

    class Config:
        from_attributes = True


class PromotionOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None = None
    price_cents: int
    image: str | None = None
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    promotion_type_id: str | None = None
    branch_ids: list[int] = []
    items: list[PromotionItemOutput] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PromotionService:
    """
    Service for promotion management.

    Business rules:
    - Promotions belong to a tenant
    - Promotions can be associated with multiple branches (PromotionBranch)
    - Promotions can contain multiple items (PromotionItem)
    - Image URLs are validated for security
    - Soft delete preserves audit trail
    """

    def __init__(self, db: Session):
        self._db = db
        self._entity_name = "Promoción"

    # =========================================================================
    # Query Methods
    # =========================================================================

    def list_all(
        self,
        tenant_id: int,
        *,
        branch_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PromotionOutput]:
        """
        List promotions with optional branch filtering.

        Args:
            tenant_id: Tenant ID for isolation.
            branch_id: Filter by specific branch.
            include_inactive: Include soft-deleted promotions.
            limit: Max results (capped at 200).
            offset: Skip count.

        Returns:
            List of PromotionOutput DTOs.
        """
        # Validate pagination
        limit = min(max(1, limit), 200)
        offset = max(0, offset)

        query = (
            select(Promotion)
            .options(
                selectinload(Promotion.branches),
                selectinload(Promotion.items),
            )
            .where(Promotion.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.where(Promotion.is_active.is_(True))

        if branch_id:
            query = query.join(PromotionBranch).where(
                PromotionBranch.branch_id == branch_id
            )
            if not include_inactive:
                query = query.where(PromotionBranch.is_active.is_(True))

        query = query.order_by(Promotion.name).offset(offset).limit(limit)
        promotions = self._db.execute(query).scalars().all()
        return [self._to_output(p) for p in promotions]

    def get_by_id(
        self,
        promotion_id: int,
        tenant_id: int,
    ) -> PromotionOutput:
        """
        Get a specific promotion with branches and items.

        Args:
            promotion_id: Promotion ID.
            tenant_id: Tenant ID.

        Returns:
            PromotionOutput DTO.

        Raises:
            NotFoundError: If promotion not found.
        """
        promotion = self._get_entity_with_relations(promotion_id, tenant_id)
        if not promotion:
            raise NotFoundError(self._entity_name, promotion_id, tenant_id=tenant_id)

        return self._to_output(promotion)

    def get_entity(
        self,
        promotion_id: int,
        tenant_id: int,
    ) -> Promotion | None:
        """Get raw entity (for internal use)."""
        return self._get_entity(promotion_id, tenant_id)

    # =========================================================================
    # Write Methods
    # =========================================================================

    def create_full(
        self,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> PromotionOutput:
        """
        Create a new promotion with branch associations and items.

        Args:
            data: Promotion data including branch_ids and items.
            tenant_id: Tenant ID.
            user_id: Creating user ID.
            user_email: Creating user email.

        Returns:
            PromotionOutput DTO.

        Raises:
            ValidationError: If invalid branch or product IDs.
        """
        branch_ids = data.pop("branch_ids", [])
        items_data = data.pop("items", [])

        # Validate branches
        self._validate_branches(branch_ids, tenant_id)

        # Validate products
        self._validate_products(items_data, tenant_id)

        # Validate and sanitize image URL
        if data.get("image"):
            data["image"] = self._validate_image(data["image"])

        # Create promotion
        promotion = Promotion(tenant_id=tenant_id, **data)
        set_created_by(promotion, user_id, user_email)
        self._db.add(promotion)
        self._db.flush()

        # Create branch associations
        for branch_id in branch_ids:
            pb = PromotionBranch(
                tenant_id=tenant_id,
                promotion_id=promotion.id,
                branch_id=branch_id,
            )
            self._db.add(pb)

        # Create items
        for item in items_data:
            pi = PromotionItem(
                tenant_id=tenant_id,
                promotion_id=promotion.id,
                product_id=item["product_id"],
                quantity=item.get("quantity", 1),
            )
            self._db.add(pi)

        self._db.commit()
        self._db.refresh(promotion)

        logger.info(
            "Promotion created",
            promotion_id=promotion.id,
            name=promotion.name,
            tenant_id=tenant_id,
        )

        return self._to_output_with_query(promotion)

    def update_full(
        self,
        promotion_id: int,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> PromotionOutput:
        """
        Update a promotion and optionally its branches and items.

        Args:
            promotion_id: Promotion ID.
            data: Update data, may include branch_ids and items.
            tenant_id: Tenant ID.
            user_id: Updating user ID.
            user_email: Updating user email.

        Returns:
            PromotionOutput DTO.

        Raises:
            NotFoundError: If promotion not found.
            ValidationError: If invalid branch or product IDs.
        """
        promotion = self._get_entity(promotion_id, tenant_id)
        if not promotion:
            raise NotFoundError(self._entity_name, promotion_id, tenant_id=tenant_id)

        branch_ids = data.pop("branch_ids", None)
        items_data = data.pop("items", None)

        # Validate and sanitize image URL
        if "image" in data and data["image"]:
            data["image"] = self._validate_image(data["image"])

        # Update basic fields
        for key, value in data.items():
            if hasattr(promotion, key):
                setattr(promotion, key, value)

        set_updated_by(promotion, user_id, user_email)

        # Update branch associations if provided
        if branch_ids is not None:
            self._validate_branches(branch_ids, tenant_id)
            self._replace_branches(promotion_id, branch_ids, tenant_id, user_id, user_email)

        # Update items if provided
        if items_data is not None:
            self._validate_products(items_data, tenant_id)
            self._replace_items(promotion_id, items_data, tenant_id, user_id, user_email)

        self._db.commit()
        self._db.refresh(promotion)

        logger.info(
            "Promotion updated",
            promotion_id=promotion_id,
            tenant_id=tenant_id,
        )

        return self._to_output_with_query(promotion)

    def delete_promotion(
        self,
        promotion_id: int,
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """
        Soft delete a promotion. Requires ADMIN role (validated at router level).

        Args:
            promotion_id: Promotion ID.
            tenant_id: Tenant ID.
            user_id: Deleting user ID.
            user_email: Deleting user email.

        Raises:
            NotFoundError: If promotion not found.
        """
        promotion = self._get_entity(promotion_id, tenant_id)
        if not promotion:
            raise NotFoundError(self._entity_name, promotion_id, tenant_id=tenant_id)

        promotion_name = promotion.name

        soft_delete(self._db, promotion, user_id, user_email)

        publish_entity_deleted(
            tenant_id=tenant_id,
            entity_type="promotion",
            entity_id=promotion_id,
            entity_name=promotion_name,
            actor_user_id=user_id,
        )

        logger.info(
            "Promotion deleted",
            promotion_id=promotion_id,
            tenant_id=tenant_id,
        )

    # =========================================================================
    # Private Helpers - Entity Retrieval
    # =========================================================================

    def _get_entity(self, promotion_id: int, tenant_id: int) -> Promotion | None:
        """Get promotion entity without relations."""
        return self._db.scalar(
            select(Promotion).where(
                Promotion.id == promotion_id,
                Promotion.tenant_id == tenant_id,
                Promotion.is_active.is_(True),
            )
        )

    def _get_entity_with_relations(
        self, promotion_id: int, tenant_id: int
    ) -> Promotion | None:
        """Get promotion entity with branches and items loaded."""
        return self._db.scalar(
            select(Promotion)
            .options(
                selectinload(Promotion.branches),
                selectinload(Promotion.items),
            )
            .where(
                Promotion.id == promotion_id,
                Promotion.tenant_id == tenant_id,
                Promotion.is_active.is_(True),
            )
        )

    # =========================================================================
    # Private Helpers - Validation
    # =========================================================================

    def _validate_branches(self, branch_ids: list[int], tenant_id: int) -> None:
        """Validate all branches belong to tenant."""
        for branch_id in branch_ids:
            branch = self._db.scalar(
                select(Branch).where(
                    Branch.id == branch_id,
                    Branch.tenant_id == tenant_id,
                )
            )
            if not branch:
                raise ValidationError(
                    f"Sucursal inválida: {branch_id}",
                    field="branch_ids",
                )

    def _validate_products(self, items: list[dict], tenant_id: int) -> None:
        """Validate all products belong to tenant."""
        for item in items:
            product_id = item.get("product_id")
            product = self._db.scalar(
                select(Product).where(
                    Product.id == product_id,
                    Product.tenant_id == tenant_id,
                )
            )
            if not product:
                raise ValidationError(
                    f"Producto inválido: {product_id}",
                    field="items",
                )

    def _validate_image(self, image_url: str) -> str:
        """Validate and sanitize image URL."""
        try:
            return validate_image_url(image_url)
        except ValueError as e:
            raise ValidationError(str(e), field="image")

    # =========================================================================
    # Private Helpers - Related Entity Management
    # =========================================================================

    def _replace_branches(
        self,
        promotion_id: int,
        branch_ids: list[int],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Replace promotion branches (soft delete old, create new)."""
        # Soft delete existing
        self._db.execute(
            update(PromotionBranch)
            .where(PromotionBranch.promotion_id == promotion_id)
            .where(PromotionBranch.is_active.is_(True))
            .values(
                is_active=False,
                deleted_at=datetime.utcnow(),
                deleted_by_id=user_id,
                deleted_by_email=user_email,
            )
        )

        # Create new
        for branch_id in branch_ids:
            pb = PromotionBranch(
                tenant_id=tenant_id,
                promotion_id=promotion_id,
                branch_id=branch_id,
            )
            self._db.add(pb)

    def _replace_items(
        self,
        promotion_id: int,
        items_data: list[dict],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Replace promotion items (soft delete old, create new)."""
        # Soft delete existing
        self._db.execute(
            update(PromotionItem)
            .where(PromotionItem.promotion_id == promotion_id)
            .where(PromotionItem.is_active.is_(True))
            .values(
                is_active=False,
                deleted_at=datetime.utcnow(),
                deleted_by_id=user_id,
                deleted_by_email=user_email,
            )
        )

        # Create new
        for item in items_data:
            pi = PromotionItem(
                tenant_id=tenant_id,
                promotion_id=promotion_id,
                product_id=item["product_id"],
                quantity=item.get("quantity", 1),
            )
            self._db.add(pi)

    # =========================================================================
    # Private Helpers - Output Transformation
    # =========================================================================

    def _to_output(self, promotion: Promotion) -> PromotionOutput:
        """Build PromotionOutput from pre-loaded relations."""
        branch_ids = []
        if promotion.branches:
            branch_ids = [
                pb.branch_id
                for pb in promotion.branches
                if pb.is_active
            ]

        items = []
        if promotion.items:
            items = [
                PromotionItemOutput(
                    product_id=pi.product_id,
                    quantity=pi.quantity,
                )
                for pi in promotion.items
                if pi.is_active
            ]

        return PromotionOutput(
            id=promotion.id,
            tenant_id=promotion.tenant_id,
            name=promotion.name,
            description=promotion.description,
            price_cents=promotion.price_cents,
            image=promotion.image,
            start_date=promotion.start_date,
            end_date=promotion.end_date,
            start_time=promotion.start_time,
            end_time=promotion.end_time,
            promotion_type_id=promotion.promotion_type_id,
            branch_ids=branch_ids,
            items=items,
            is_active=promotion.is_active,
            created_at=promotion.created_at,
            updated_at=promotion.updated_at,
        )

    def _to_output_with_query(self, promotion: Promotion) -> PromotionOutput:
        """Build PromotionOutput with separate queries for relations."""
        branch_relations = self._db.execute(
            select(PromotionBranch).where(
                PromotionBranch.promotion_id == promotion.id,
                PromotionBranch.is_active.is_(True),
            )
        ).scalars().all()
        branch_ids = [pb.branch_id for pb in branch_relations]

        item_relations = self._db.execute(
            select(PromotionItem).where(
                PromotionItem.promotion_id == promotion.id,
                PromotionItem.is_active.is_(True),
            )
        ).scalars().all()
        items = [
            PromotionItemOutput(
                product_id=pi.product_id,
                quantity=pi.quantity,
            )
            for pi in item_relations
        ]

        return PromotionOutput(
            id=promotion.id,
            tenant_id=promotion.tenant_id,
            name=promotion.name,
            description=promotion.description,
            price_cents=promotion.price_cents,
            image=promotion.image,
            start_date=promotion.start_date,
            end_date=promotion.end_date,
            start_time=promotion.start_time,
            end_time=promotion.end_time,
            promotion_type_id=promotion.promotion_type_id,
            branch_ids=branch_ids,
            items=items,
            is_active=promotion.is_active,
            created_at=promotion.created_at,
            updated_at=promotion.updated_at,
        )
