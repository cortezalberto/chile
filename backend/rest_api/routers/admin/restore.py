"""
Entity restoration endpoints.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session,
    get_db, current_user,
    restore_entity, get_model_class, find_deleted_entity,
    get_user_id, get_user_email,
)
from shared.utils.admin_schemas import RestoreOutput


router = APIRouter(tags=["admin-restore"])


@router.post("/{entity_type}/{entity_id}/restore", response_model=RestoreOutput)
def restore_deleted_entity(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> RestoreOutput:
    """
    Restore a soft-deleted entity. Requires ADMIN role.

    Supported entity types:
    - branches, categories, subcategories, products
    - allergens, tables, staff, promotions
    """
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    # Get the model class for this entity type
    model_class = get_model_class(entity_type)
    if not model_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}",
        )

    # Find the soft-deleted entity
    entity = find_deleted_entity(db, model_class, entity_id)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} not found or already active",
        )

    # Verify tenant ownership
    if hasattr(entity, 'tenant_id') and entity.tenant_id != user["tenant_id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} not found",
        )

    # Restore the entity
    restore_entity(db, entity, get_user_id(user), get_user_email(user))

    # Get entity name for response
    entity_name = getattr(entity, 'name', None) or getattr(entity, 'code', None) or getattr(entity, 'email', None) or str(entity_id)

    return RestoreOutput(
        success=True,
        message=f"{entity_type} '{entity_name}' restored successfully",
        entity_type=entity_type,
        entity_id=entity_id,
    )
