"""
Tenant (Restaurant) management endpoints.
"""

from fastapi import APIRouter, HTTPException, status

from rest_api.routers.admin._base import (
    Depends, Session, select,
    get_db, current_user, Tenant,
    require_admin,
)
from shared.utils.admin_schemas import TenantOutput, TenantUpdate
from shared.config.logging import rest_api_logger as logger


router = APIRouter(tags=["admin-tenant"])


@router.get("/tenant", response_model=TenantOutput)
def get_tenant(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TenantOutput:
    """Get current user's tenant (restaurant) information."""
    tenant = db.scalar(select(Tenant).where(Tenant.id == user["tenant_id"]))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantOutput.model_validate(tenant)


@router.patch("/tenant", response_model=TenantOutput)
def update_tenant(
    body: TenantUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> TenantOutput:
    """Update tenant information. Requires ADMIN role."""
    tenant = db.scalar(select(Tenant).where(Tenant.id == user["tenant_id"]))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(tenant)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update tenant", tenant_id=tenant.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tenant - please try again",
        )
    return TenantOutput.model_validate(tenant)

