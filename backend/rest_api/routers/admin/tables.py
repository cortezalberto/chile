"""
Table management endpoints including batch creation.

PERF-BGTASK-01: Uses FastAPI BackgroundTasks for event publishing.
"""

import re
from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from rest_api.routers.admin._base import (
    Depends, Session, select,
    get_db, current_user, Table, Branch, BranchSector,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin, require_admin_or_manager,
    is_admin, validate_branch_access, filter_by_accessible_branches,
    Round, TableSession,
)
from shared.utils.admin_schemas import (
    TableOutput, TableCreate, TableUpdate,
    TableBulkCreate, TableBulkResult,
)
from shared.config.logging import rest_api_logger as logger
from shared.utils.admin_schemas import (
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
    """List tables, optionally filtered by branch.

    MANAGER users only see tables from their assigned branches.
    Includes active_round_statuses for Dashboard order status calculation.
    """
    tenant_id = user["tenant_id"]
    query = select(Table).where(Table.tenant_id == tenant_id)

    # MANAGER branch isolation
    branch_ids_filter, should_filter = filter_by_accessible_branches(user, branch_id)
    if should_filter:
        if not branch_ids_filter:
            return []  # No access to any branch
        query = query.where(Table.branch_id.in_(branch_ids_filter))

    if not include_deleted:
        query = query.where(Table.is_active.is_(True))

    tables = db.execute(query.order_by(Table.branch_id, Table.code)).scalars().all()

    if not tables:
        return []

    # Get all table IDs to query active rounds
    table_ids = [t.id for t in tables]

    # Query active sessions and their rounds in a single query
    # Active rounds = rounds from OPEN/PAYING sessions with status not SERVED/CANCELED
    active_rounds_query = (
        select(Round.id, Round.status, TableSession.table_id)
        .join(TableSession, Round.table_session_id == TableSession.id)
        .where(
            TableSession.table_id.in_(table_ids),
            TableSession.status.in_(["OPEN", "PAYING"]),
            Round.tenant_id == tenant_id,
            Round.status.notin_(["SERVED", "CANCELED", "DRAFT"]),
        )
    )
    active_rounds = db.execute(active_rounds_query).all()

    # Build lookup: table_id -> {round_id: status}
    table_round_statuses: dict[int, dict[int, str]] = {t.id: {} for t in tables}
    for round_id, round_status, table_id in active_rounds:
        table_round_statuses[table_id][round_id] = round_status

    # Build response with active_round_statuses
    result = []
    for table in tables:
        output = TableOutput.model_validate(table)
        output.active_round_statuses = table_round_statuses.get(table.id, {})
        result.append(output)

    return result


@router.get("/tables/{table_id}", response_model=TableOutput)
def get_table(
    table_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableOutput:
    """Get a specific table by ID.

    MANAGER users can only access tables from their assigned branches.
    """
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active.is_(True),
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, table.branch_id)

    return TableOutput.model_validate(table)


@router.post("/tables", response_model=TableOutput, status_code=status.HTTP_201_CREATED)
def create_table(
    body: TableCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> TableOutput:
    """Create a new table. Requires ADMIN or MANAGER role.

    MANAGER users can only create tables in their assigned branches.
    """
    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, body.branch_id)

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

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(table)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create table", branch_id=body.branch_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create table - please try again",
        )
    return TableOutput.model_validate(table)


@router.patch("/tables/{table_id}", response_model=TableOutput)
def update_table(
    table_id: int,
    body: TableUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> TableOutput:
    """Update a table. Requires ADMIN or MANAGER role.

    MANAGER users can only update tables in their assigned branches.
    """
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active.is_(True),
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, table.branch_id)

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(table, key, value)

    set_updated_by(table, get_user_id(user), get_user_email(user))

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(table)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update table", table_id=table_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update table - please try again",
        )
    return TableOutput.model_validate(table)


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(
    table_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> None:
    """Soft delete a table. Requires ADMIN or MANAGER role.

    MANAGER users can only delete tables in their assigned branches.
    PERF-BGTASK-01: Uses BackgroundTasks for async event publishing.
    """
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active.is_(True),
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, table.branch_id)

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
        background_tasks=background_tasks,
    )


@router.post("/tables/batch", response_model=TableBulkResult, status_code=status.HTTP_201_CREATED)
def batch_create_tables(
    body: TableBulkCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> TableBulkResult:
    """Batch create tables for a branch by sector. Requires ADMIN or MANAGER role.

    MANAGER users can only create tables in their assigned branches.
    """
    tenant_id = user["tenant_id"]

    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, body.branch_id)

    branch = db.scalar(
        select(Branch).where(
            Branch.id == body.branch_id,
            Branch.tenant_id == tenant_id,
            Branch.is_active.is_(True),
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
                    BranchSector.is_active.is_(True),
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

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        for table in created_tables:
            db.refresh(table)
    except Exception as e:
        db.rollback()
        logger.error("Failed to batch create tables", branch_id=body.branch_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tables - please try again",
        )

    return TableBulkResult(
        created_count=len(created_tables),
        tables=[TableOutput.model_validate(t) for t in created_tables],
    )
