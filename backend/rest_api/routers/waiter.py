"""
Waiter router.
Handles operations performed by waiters.
PWAW-C001: Service call acknowledge/resolve endpoints.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, or_

from rest_api.db import get_db
from rest_api.models import (
    BranchSector,
    ServiceCall,
    Table,
    TableSession,
    WaiterSectorAssignment,
)
from shared.auth import current_user_context, require_roles
from shared.schemas import ServiceCallOutput
from shared.logging import waiter_logger as logger
from shared.events import (
    get_redis_client,
    publish_service_call_event,
    SERVICE_CALL_ACKED,
    SERVICE_CALL_CLOSED,
)


# =============================================================================
# Schemas
# =============================================================================


class SectorAssignmentOutput(BaseModel):
    """Output schema for a sector assignment."""
    sector_id: int
    sector_name: str
    sector_prefix: str
    branch_id: int
    assignment_date: date
    shift: Optional[str] = None


class MyAssignmentsOutput(BaseModel):
    """Output schema for waiter's current assignments."""
    waiter_id: int
    assignment_date: date
    sectors: list[SectorAssignmentOutput]
    sector_ids: list[int]  # Convenience list for filtering


router = APIRouter(prefix="/api/waiter", tags=["waiter"])


# =============================================================================
# Service Calls
# =============================================================================


@router.get("/service-calls", response_model=list[ServiceCallOutput])
def get_pending_service_calls(
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[ServiceCallOutput]:
    """
    Get all pending service calls for the waiter's branches.

    Returns service calls with status OPEN or ACKED.
    PWAW-A003: List endpoint for service calls.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    branch_ids = ctx.get("branch_ids", [])
    if not branch_ids:
        return []

    # Get pending service calls with eager loading to avoid N+1 queries
    # - joinedload for session->table chain (many-to-one relationships)
    calls = db.execute(
        select(ServiceCall)
        .options(
            joinedload(ServiceCall.session).joinedload(TableSession.table),
        )
        .where(
            ServiceCall.branch_id.in_(branch_ids),
            ServiceCall.status.in_(["OPEN", "ACKED"]),
        )
        .order_by(ServiceCall.created_at.asc())
    ).scalars().unique().all()

    result = []
    for call in calls:
        # Access pre-loaded relationships (no additional queries)
        session = call.session
        table = session.table if session else None

        result.append(
            ServiceCallOutput(
                id=call.id,
                type=call.type,
                status=call.status,
                created_at=call.created_at,
                acked_at=call.acked_at if hasattr(call, 'acked_at') else None,
                acked_by_user_id=call.acked_by_user_id,
                table_id=table.id if table else None,
                table_code=table.code if table else None,
                session_id=call.table_session_id,
            )
        )

    return result


@router.post("/service-calls/{call_id}/acknowledge", response_model=ServiceCallOutput)
async def acknowledge_service_call(
    call_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ServiceCallOutput:
    """
    Acknowledge a service call.

    Changes status from OPEN to ACKED, indicating waiter is aware
    and will attend to the table.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # Find the service call with eager loading for session and table
    call = db.scalar(
        select(ServiceCall)
        .options(
            joinedload(ServiceCall.session).joinedload(TableSession.table),
        )
        .where(ServiceCall.id == call_id)
    )

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service call {call_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if call.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Verify status
    if call.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot acknowledge call with status {call.status}",
        )

    # Update status
    user_id = int(ctx["sub"])
    call.status = "ACKED"
    call.acked_by_user_id = user_id
    if hasattr(call, 'acked_at'):
        call.acked_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(call)

    # Access pre-loaded relationships (no additional queries)
    session = call.session
    table = session.table if session else None

    # Publish event
    redis = None
    try:
        redis = await get_redis_client()
        await publish_service_call_event(
            redis_client=redis,
            event_type=SERVICE_CALL_ACKED,
            tenant_id=call.tenant_id,
            branch_id=call.branch_id,
            table_id=table.id if table else 0,
            session_id=call.table_session_id,
            call_id=call.id,
            call_type=call.type,
            actor_user_id=user_id,
            actor_role="WAITER",
        )
        logger.info("Service call acknowledged", call_id=call_id, user_id=user_id)
    except Exception as e:
        logger.error("Failed to publish SERVICE_CALL_ACKED event", call_id=call_id, error=str(e))
    finally:
        if redis:
            await redis.close()

    return ServiceCallOutput(
        id=call.id,
        type=call.type,
        status=call.status,
        created_at=call.created_at,
        acked_at=call.acked_at if hasattr(call, 'acked_at') else None,
        acked_by_user_id=call.acked_by_user_id,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        session_id=call.table_session_id,
    )


@router.post("/service-calls/{call_id}/resolve", response_model=ServiceCallOutput)
async def resolve_service_call(
    call_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ServiceCallOutput:
    """
    Resolve a service call.

    Changes status to CLOSED, indicating the request has been fulfilled.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # Find the service call with eager loading for session and table
    call = db.scalar(
        select(ServiceCall)
        .options(
            joinedload(ServiceCall.session).joinedload(TableSession.table),
        )
        .where(ServiceCall.id == call_id)
    )

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service call {call_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if call.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Verify status (can resolve from OPEN or ACKED)
    if call.status not in ["OPEN", "ACKED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resolve call with status {call.status}",
        )

    # Update status
    user_id = int(ctx["sub"])
    call.status = "CLOSED"
    if hasattr(call, 'resolved_at'):
        call.resolved_at = datetime.now(timezone.utc)
    if hasattr(call, 'resolved_by_user_id'):
        call.resolved_by_user_id = user_id

    db.commit()
    db.refresh(call)

    # Access pre-loaded relationships (no additional queries)
    session = call.session
    table = session.table if session else None

    # Publish event
    redis = None
    try:
        redis = await get_redis_client()
        await publish_service_call_event(
            redis_client=redis,
            event_type=SERVICE_CALL_CLOSED,
            tenant_id=call.tenant_id,
            branch_id=call.branch_id,
            table_id=table.id if table else 0,
            session_id=call.table_session_id,
            call_id=call.id,
            call_type=call.type,
            actor_user_id=user_id,
            actor_role="WAITER",
        )
        logger.info("Service call resolved", call_id=call_id, user_id=user_id)
    except Exception as e:
        logger.error("Failed to publish SERVICE_CALL_CLOSED event", call_id=call_id, error=str(e))
    finally:
        if redis:
            await redis.close()

    return ServiceCallOutput(
        id=call.id,
        type=call.type,
        status=call.status,
        created_at=call.created_at,
        acked_at=call.acked_at if hasattr(call, 'acked_at') else None,
        acked_by_user_id=call.acked_by_user_id,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        session_id=call.table_session_id,
    )


# =============================================================================
# Sector Assignments
# =============================================================================


@router.get("/my-assignments", response_model=MyAssignmentsOutput)
def get_my_sector_assignments(
    assignment_date: date = Query(default=None, description="Date for assignments (defaults to today)"),
    shift: Optional[str] = Query(default=None, description="Filter by shift: MORNING, AFTERNOON, NIGHT"),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> MyAssignmentsOutput:
    """
    Get the current waiter's sector assignments for today (or specified date).

    Returns all sectors the waiter is assigned to, along with their IDs
    for use in WebSocket filtering.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    target_date = assignment_date or date.today()

    # Query assignments for this waiter on this date
    query = (
        select(WaiterSectorAssignment)
        .options(joinedload(WaiterSectorAssignment.sector))
        .where(
            WaiterSectorAssignment.waiter_id == waiter_id,
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.assignment_date == target_date,
            WaiterSectorAssignment.is_active == True,
        )
    )

    if shift:
        # Include assignments for specific shift OR all-day (NULL shift)
        query = query.where(
            or_(
                WaiterSectorAssignment.shift == shift,
                WaiterSectorAssignment.shift.is_(None),
            )
        )

    assignments = db.execute(query).scalars().unique().all()

    sectors = []
    sector_ids = []

    for assignment in assignments:
        sector = assignment.sector
        if sector and sector.is_active:
            sectors.append(
                SectorAssignmentOutput(
                    sector_id=sector.id,
                    sector_name=sector.name,
                    sector_prefix=sector.prefix,
                    branch_id=assignment.branch_id,
                    assignment_date=assignment.assignment_date,
                    shift=assignment.shift,
                )
            )
            if sector.id not in sector_ids:
                sector_ids.append(sector.id)

    return MyAssignmentsOutput(
        waiter_id=waiter_id,
        assignment_date=target_date,
        sectors=sectors,
        sector_ids=sector_ids,
    )


@router.get("/my-tables", response_model=list[dict])
def get_my_assigned_tables(
    assignment_date: date = Query(default=None, description="Date for assignments (defaults to today)"),
    shift: Optional[str] = Query(default=None, description="Filter by shift"),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[dict]:
    """
    Get all tables in the sectors the waiter is assigned to.

    Useful for filtering which tables to show in the waiter's UI.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])
    target_date = assignment_date or date.today()

    # Get assigned sector IDs
    query = (
        select(WaiterSectorAssignment.sector_id)
        .where(
            WaiterSectorAssignment.waiter_id == waiter_id,
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.assignment_date == target_date,
            WaiterSectorAssignment.is_active == True,
        )
    )

    if shift:
        query = query.where(
            or_(
                WaiterSectorAssignment.shift == shift,
                WaiterSectorAssignment.shift.is_(None),
            )
        )

    sector_ids = db.execute(query).scalars().all()

    if not sector_ids:
        # No assignments - return all tables in branches (fallback behavior)
        tables = db.execute(
            select(Table)
            .where(
                Table.branch_id.in_(branch_ids),
                Table.is_active == True,
            )
            .order_by(Table.branch_id, Table.code)
        ).scalars().all()
    else:
        # Return only tables in assigned sectors
        tables = db.execute(
            select(Table)
            .options(joinedload(Table.sector_rel))
            .where(
                Table.sector_id.in_(sector_ids),
                Table.is_active == True,
            )
            .order_by(Table.branch_id, Table.code)
        ).scalars().unique().all()

    return [
        {
            "id": t.id,
            "code": t.code,
            "capacity": t.capacity,
            "status": t.status,
            "branch_id": t.branch_id,
            "sector_id": t.sector_id,
            "sector_name": t.sector_rel.name if t.sector_rel else t.sector,
        }
        for t in tables
    ]
