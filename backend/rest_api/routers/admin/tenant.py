"""
Tenant (Restaurant) management endpoints.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    get_db, current_user, Tenant,
    require_admin,
)
from shared.utils.admin_schemas import TenantOutput, TenantUpdate


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

    db.commit()
    db.refresh(tenant)
    return TenantOutput.model_validate(tenant)
