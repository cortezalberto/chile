"""
Table management endpoints including batch creation.
"""

import re
from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    get_db, current_user, Table, Branch, BranchSector,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin,
)
from rest_api.routers.admin_schemas import (
    TableOutput, TableCreate, TableUpdate,
    TableBulkCreate, TableBulkResult,
)


router = APIRouter(tags=["admin-tables"])


def _generate_table_codes(db: Session, tenant_id: int, branch_id: int, prefix: str, count: int) -> list[str]:
    """Generate unique sequential table codes for a branch."""
    existing = db.execute(
        select(Table.code).where(
            Table.tenant_id == tenant_id,
            Table.branch_id == branch_id,
            Table.code.like(f"{prefix}-%"),
        )
    ).scalars().all()

    existing_numbers = set()
    for code in existing:
        match = re.match(rf'^{re.escape(prefix)}-(\d+)$', code)
        if match:
            existing_numbers.add(int(match.group(1)))

    codes = []
    next_num = 1
    while len(codes) < count:
        if next_num not in existing_numbers:
            codes.append(f"{prefix}-{next_num:02d}")
        next_num += 1

    return codes


@router.get("/tables", response_model=list[TableOutput])
def list_tables(
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[TableOutput]:
    """List tables, optionally filtered by branch."""
    query = select(Table).where(Table.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Table.is_active == True)

    if branch_id:
        query = query.where(Table.branch_id == branch_id)

    tables = db.execute(query.order_by(Table.branch_id, Table.code)).scalars().all()
    return [TableOutput.model_validate(t) for t in tables]


@router.get("/tables/{table_id}", response_model=TableOutput)
def get_table(
    table_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableOutput:
    """Get a specific table by ID."""
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active == True,
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )
    return TableOutput.model_validate(table)


@router.post("/tables", response_model=TableOutput, status_code=status.HTTP_201_CREATED)
def create_table(
    body: TableCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableOutput:
    """Create a new table."""
    branch = db.scalar(
        select(Branch).where(
            Branch.id == body.branch_id,
            Branch.tenant_id == user["tenant_id"],
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch_id",
        )

    table = Table(
        tenant_id=user["tenant_id"],
        **body.model_dump(),
    )
    set_created_by(table, get_user_id(user), get_user_email(user))
    db.add(table)
    db.commit()
    db.refresh(table)
    return TableOutput.model_validate(table)


@router.patch("/tables/{table_id}", response_model=TableOutput)
def update_table(
    table_id: int,
    body: TableUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableOutput:
    """Update a table."""
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active == True,
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(table, key, value)

    set_updated_by(table, get_user_id(user), get_user_email(user))

    db.commit()
    db.refresh(table)
    return TableOutput.model_validate(table)


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(
    table_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a table. Requires ADMIN role."""
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active == True,
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    table_code = table.code
    branch_id = table.branch_id
    tenant_id = table.tenant_id

    soft_delete(db, table, get_user_id(user), get_user_email(user))

    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="table",
        entity_id=table_id,
        entity_name=table_code,
        branch_id=branch_id,
        actor_user_id=get_user_id(user),
    )


@router.post("/tables/batch", response_model=TableBulkResult, status_code=status.HTTP_201_CREATED)
def batch_create_tables(
    body: TableBulkCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableBulkResult:
    """Batch create tables for a branch by sector."""
    tenant_id = user["tenant_id"]

    branch = db.scalar(
        select(Branch).where(
            Branch.id == body.branch_id,
            Branch.tenant_id == tenant_id,
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch_id",
        )

    created_tables: list[Table] = []
    sector_cache: dict[int, BranchSector] = {}

    for item in body.tables:
        if item.sector_id not in sector_cache:
            sector = db.scalar(
                select(BranchSector).where(
                    BranchSector.id == item.sector_id,
                    BranchSector.tenant_id == tenant_id,
                    BranchSector.is_active == True,
                )
            )
            if not sector:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sector_id: {item.sector_id}",
                )
            sector_cache[item.sector_id] = sector

        sector = sector_cache[item.sector_id]

        codes = _generate_table_codes(
            db, tenant_id, body.branch_id, sector.prefix, item.count
        )

        for code in codes:
            table = Table(
                tenant_id=tenant_id,
                branch_id=body.branch_id,
                code=code,
                capacity=item.capacity,
                sector=sector.name,
                status="FREE",
            )
            set_created_by(table, get_user_id(user), get_user_email(user))
            db.add(table)
            created_tables.append(table)

    db.commit()

    for table in created_tables:
        db.refresh(table)

    return TableBulkResult(
        created_count=len(created_tables),
        tables=[TableOutput.model_validate(t) for t in created_tables],
    )
