"""
Soft Delete Service for consistent soft delete operations across all entities.

This service provides functions to:
- Soft delete entities (set is_active=False with audit trail)
- Restore soft-deleted entities
- Set created_by/updated_by audit fields
"""

from datetime import datetime
from typing import TypeVar, Type
from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.models import (
    AuditMixin,
    Branch,
    Category,
    Subcategory,
    Product,
    BranchProduct,
    Allergen,
    Table,
    User,
    UserBranchRole,
    Promotion,
    PromotionBranch,
    PromotionItem,
    Tenant,
    TableSession,
    Diner,
    Round,
    RoundItem,
    KitchenTicket,
    KitchenTicketItem,
    ServiceCall,
    Check,
    Payment,
    Charge,
    Allocation,
    KnowledgeDocument,
    ChatLog,
    AuditLog,
)


# Type variable for generic entity operations
T = TypeVar("T", bound=AuditMixin)


# Model mapping for restore endpoint
MODEL_MAP: dict[str, Type[AuditMixin]] = {
    "branches": Branch,
    "categories": Category,
    "subcategories": Subcategory,
    "products": Product,
    "branch_products": BranchProduct,
    "allergens": Allergen,
    "tables": Table,
    "users": User,
    "staff": User,  # Alias for staff
    "user_branch_roles": UserBranchRole,
    "promotions": Promotion,
    "promotion_branches": PromotionBranch,
    "promotion_items": PromotionItem,
    "tenants": Tenant,
    "table_sessions": TableSession,
    "diners": Diner,
    "rounds": Round,
    "round_items": RoundItem,
    "kitchen_tickets": KitchenTicket,
    "kitchen_ticket_items": KitchenTicketItem,
    "service_calls": ServiceCall,
    "checks": Check,
    "payments": Payment,
    "charges": Charge,
    "allocations": Allocation,
    "knowledge_documents": KnowledgeDocument,
    "chat_logs": ChatLog,
    "audit_logs": AuditLog,
}


def soft_delete(db: Session, entity: T, user_id: int, user_email: str) -> T:
    """
    Perform soft delete on an entity with audit trail.

    SVC-MED-07 FIX: Added try-except with rollback for transaction safety.

    Args:
        db: Database session
        entity: The entity to soft delete (must inherit from AuditMixin)
        user_id: ID of the user performing the deletion
        user_email: Email of the user performing the deletion

    Returns:
        The soft-deleted entity

    Raises:
        Exception: Re-raises any exception after rollback
    """
    entity.soft_delete(user_id, user_email)
    try:
        db.commit()
        db.refresh(entity)
    except Exception:
        db.rollback()
        raise
    return entity


def restore_entity(db: Session, entity: T, user_id: int, user_email: str) -> T:
    """
    Restore a soft-deleted entity.

    SVC-MED-06 FIX: Added null check and try-except with rollback.

    Args:
        db: Database session
        entity: The entity to restore (must inherit from AuditMixin)
        user_id: ID of the user performing the restoration
        user_email: Email of the user performing the restoration

    Returns:
        The restored entity

    Raises:
        ValueError: If entity is None
        Exception: Re-raises any exception after rollback
    """
    # SVC-MED-06 FIX: Null check for entity
    if entity is None:
        raise ValueError("Cannot restore None entity")

    entity.restore(user_id, user_email)
    try:
        db.commit()
        db.refresh(entity)
    except Exception:
        db.rollback()
        raise
    return entity


def set_created_by(entity: T, user_id: int, user_email: str) -> T:
    """
    Set created_by fields on a new entity.

    Args:
        entity: The entity being created
        user_id: ID of the user creating the entity
        user_email: Email of the user creating the entity

    Returns:
        The entity with created_by fields set
    """
    entity.set_created_by(user_id, user_email)
    return entity


def set_updated_by(entity: T, user_id: int, user_email: str) -> T:
    """
    Set updated_by fields on an entity being updated.

    Args:
        entity: The entity being updated
        user_id: ID of the user updating the entity
        user_email: Email of the user updating the entity

    Returns:
        The entity with updated_by fields set
    """
    entity.set_updated_by(user_id, user_email)
    return entity


def get_model_class(entity_type: str) -> Type[AuditMixin] | None:
    """
    Get the model class for a given entity type string.

    Args:
        entity_type: The entity type name (e.g., "branches", "products")

    Returns:
        The model class or None if not found
    """
    return MODEL_MAP.get(entity_type.lower())


def find_active_entity(db: Session, model_class: Type[T], entity_id: int) -> T | None:
    """
    Find an active entity by ID.

    Args:
        db: Database session
        model_class: The model class to query
        entity_id: The ID of the entity

    Returns:
        The entity if found and active, None otherwise
    """
    # MED-29-09 FIX: Use modern SQLAlchemy 2.0 select() instead of deprecated query() API
    # HIGH-03 FIX: Use .is_(True) for proper SQL boolean comparison
    return db.scalar(
        select(model_class).where(
            model_class.id == entity_id,
            model_class.is_active.is_(True),
        )
    )


def find_deleted_entity(db: Session, model_class: Type[T], entity_id: int) -> T | None:
    """
    Find a soft-deleted entity by ID.

    Args:
        db: Database session
        model_class: The model class to query
        entity_id: The ID of the entity

    Returns:
        The entity if found and deleted, None otherwise
    """
    # MED-29-09 FIX: Use modern SQLAlchemy 2.0 select() instead of deprecated query() API
    # HIGH-03 FIX: Use .is_(False) for proper SQL boolean comparison
    return db.scalar(
        select(model_class).where(
            model_class.id == entity_id,
            model_class.is_active.is_(False),
        )
    )


def filter_active(query, model_class: Type[T], include_deleted: bool = False):
    """
    Apply is_active filter to a query.

    Args:
        query: The SQLAlchemy query to filter
        model_class: The model class being queried
        include_deleted: If True, include soft-deleted entities

    Returns:
        The filtered query
    """
    # HIGH-03 FIX: Use .is_(True) for proper SQL boolean comparison
    if not include_deleted:
        return query.filter(model_class.is_active.is_(True))
    return query


# =============================================================================
# CRIT-01 FIX: Cascade Delete with Audit Trail Preservation
# =============================================================================

# Define cascade relationships: parent_model -> list of (child_model, foreign_key)
CASCADE_RELATIONSHIPS: dict[type, list[tuple[type, str]]] = {
    Product: [
        # ProductAllergen, ProductIngredient, BranchProduct are children
    ],
    Category: [
        (Subcategory, "category_id"),
    ],
    Branch: [
        (Table, "branch_id"),
    ],
    Promotion: [
        (PromotionBranch, "promotion_id"),
        (PromotionItem, "promotion_id"),
    ],
    TableSession: [
        (Diner, "session_id"),
        (Round, "session_id"),
        (ServiceCall, "session_id"),
        (Check, "session_id"),
    ],
    Round: [
        (RoundItem, "round_id"),
        (KitchenTicket, "round_id"),
    ],
    KitchenTicket: [
        (KitchenTicketItem, "ticket_id"),
    ],
    Check: [
        (Charge, "check_id"),
        (Payment, "check_id"),
    ],
}


def cascade_soft_delete(
    db: Session,
    entity: T,
    user_id: int,
    user_email: str,
    commit: bool = True,
) -> list[dict]:
    """
    CRIT-01 FIX: Perform soft delete with cascade to preserve audit trail.

    Instead of relying on ORM cascade="delete-orphan" which hard deletes,
    this function soft-deletes children to preserve the audit history.

    Args:
        db: Database session
        entity: The parent entity to soft delete
        user_id: ID of the user performing the deletion
        user_email: Email of the user performing the deletion
        commit: Whether to commit the transaction (default True)

    Returns:
        List of affected entities: [{"type": str, "id": int, "name": str}]
    """
    affected: list[dict] = []
    entity_type = type(entity)

    # Get cascade relationships for this entity type
    relationships = CASCADE_RELATIONSHIPS.get(entity_type, [])

    # Soft delete children first (depth-first)
    for child_model, foreign_key in relationships:
        children = db.execute(
            select(child_model).where(
                getattr(child_model, foreign_key) == entity.id,
                child_model.is_active.is_(True),
            )
        ).scalars().all()

        for child in children:
            # Recursively cascade to grandchildren
            child_affected = cascade_soft_delete(
                db, child, user_id, user_email, commit=False
            )
            affected.extend(child_affected)

            # Soft delete this child
            child.soft_delete(user_id, user_email)
            affected.append({
                "type": child_model.__tablename__,
                "id": child.id,
                "name": getattr(child, "name", None) or getattr(child, "code", None) or str(child.id),
            })

    # Soft delete the parent entity
    entity.soft_delete(user_id, user_email)

    if commit:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return affected


def cascade_restore(
    db: Session,
    entity: T,
    user_id: int,
    user_email: str,
    restore_children: bool = True,
    commit: bool = True,
) -> list[dict]:
    """
    CRIT-01 FIX: Restore a soft-deleted entity and optionally its children.

    Args:
        db: Database session
        entity: The parent entity to restore
        user_id: ID of the user performing the restoration
        user_email: Email of the user performing the restoration
        restore_children: Whether to also restore child entities
        commit: Whether to commit the transaction

    Returns:
        List of restored entities: [{"type": str, "id": int, "name": str}]
    """
    restored: list[dict] = []
    entity_type = type(entity)

    # Restore the parent entity first
    entity.restore(user_id, user_email)
    restored.append({
        "type": entity_type.__tablename__,
        "id": entity.id,
        "name": getattr(entity, "name", None) or str(entity.id),
    })

    if restore_children:
        # Get cascade relationships for this entity type
        relationships = CASCADE_RELATIONSHIPS.get(entity_type, [])

        for child_model, foreign_key in relationships:
            # Find soft-deleted children that were deleted around the same time
            children = db.execute(
                select(child_model).where(
                    getattr(child_model, foreign_key) == entity.id,
                    child_model.is_active.is_(False),
                )
            ).scalars().all()

            for child in children:
                child_restored = cascade_restore(
                    db, child, user_id, user_email,
                    restore_children=True, commit=False
                )
                restored.extend(child_restored)

    if commit:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return restored
