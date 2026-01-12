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

from ..models import (
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

    Args:
        db: Database session
        entity: The entity to soft delete (must inherit from AuditMixin)
        user_id: ID of the user performing the deletion
        user_email: Email of the user performing the deletion

    Returns:
        The soft-deleted entity
    """
    entity.soft_delete(user_id, user_email)
    db.commit()
    db.refresh(entity)
    return entity


def restore_entity(db: Session, entity: T, user_id: int, user_email: str) -> T:
    """
    Restore a soft-deleted entity.

    Args:
        db: Database session
        entity: The entity to restore (must inherit from AuditMixin)
        user_id: ID of the user performing the restoration
        user_email: Email of the user performing the restoration

    Returns:
        The restored entity
    """
    entity.restore(user_id, user_email)
    db.commit()
    db.refresh(entity)
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
    return (
        db.query(model_class)
        .filter(model_class.id == entity_id, model_class.is_active == True)
        .first()
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
    return (
        db.query(model_class)
        .filter(model_class.id == entity_id, model_class.is_active == False)
        .first()
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
    if not include_deleted:
        return query.filter(model_class.is_active == True)
    return query
