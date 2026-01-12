"""
Diner router.
Handles operations performed by diners (customers) at tables.
Uses table token authentication instead of JWT.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from rest_api.db import get_db
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    Product,
    BranchProduct,
    ServiceCall,
    Check,
    Payment,
    Diner,
)
from shared.auth import current_table_context
from shared.schemas import (
    SubmitRoundRequest,
    SubmitRoundResponse,
    RoundOutput,
    RoundItemOutput,
    CreateServiceCallRequest,
    ServiceCallOutput,
    CheckDetailOutput,
    CheckItemOutput,
    PaymentOutput,
    RegisterDinerRequest,
    DinerOutput,
)
from shared.logging import diner_logger as logger
from shared.events import (
    get_redis_client,
    publish_round_event,
    publish_service_call_event,
    ROUND_SUBMITTED,
    SERVICE_CALL_CREATED,
)


router = APIRouter(prefix="/api/diner", tags=["diner"])


# =============================================================================
# Diner Registration (Phase 2)
# =============================================================================


@router.post("/register", response_model=DinerOutput)
def register_diner(
    body: RegisterDinerRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> DinerOutput:
    """
    Register a diner at a table session.

    Creates a persistent Diner entity that can be linked to orders and payments.
    If a diner with the same local_id already exists for this session, returns the existing diner.

    Requires X-Table-Token header with valid table token.
    """
    session_id = table_ctx["session_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # Verify session exists and is open
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active or does not exist",
        )

    # Check if diner with same local_id already exists (idempotency)
    if body.local_id:
        existing_diner = db.scalar(
            select(Diner).where(
                Diner.session_id == session_id,
                Diner.local_id == body.local_id,
            )
        )
        if existing_diner:
            return DinerOutput(
                id=existing_diner.id,
                session_id=existing_diner.session_id,
                name=existing_diner.name,
                color=existing_diner.color,
                local_id=existing_diner.local_id,
                joined_at=existing_diner.joined_at,
            )

    # Create new diner
    new_diner = Diner(
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        name=body.name,
        color=body.color,
        local_id=body.local_id,
    )
    db.add(new_diner)
    db.commit()
    db.refresh(new_diner)

    return DinerOutput(
        id=new_diner.id,
        session_id=new_diner.session_id,
        name=new_diner.name,
        color=new_diner.color,
        local_id=new_diner.local_id,
        joined_at=new_diner.joined_at,
    )


@router.get("/session/{session_id}/diners", response_model=list[DinerOutput])
def get_session_diners(
    session_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> list[DinerOutput]:
    """
    Get all diners for a session.

    Returns the list of registered diners with their backend IDs.
    """
    # Verify session matches token
    if table_ctx["session_id"] != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not match token",
        )

    diners = db.execute(
        select(Diner)
        .where(Diner.session_id == session_id)
        .order_by(Diner.joined_at)
    ).scalars().all()

    return [
        DinerOutput(
            id=diner.id,
            session_id=diner.session_id,
            name=diner.name,
            color=diner.color,
            local_id=diner.local_id,
            joined_at=diner.joined_at,
        )
        for diner in diners
    ]


# =============================================================================
# Round Submission
# =============================================================================


@router.post("/rounds/submit", response_model=SubmitRoundResponse)
async def submit_round(
    body: SubmitRoundRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> SubmitRoundResponse:
    """
    Submit a new round of orders.

    Creates a new round with the specified items and publishes
    a ROUND_SUBMITTED event for waiters and kitchen.

    Requires X-Table-Token header with valid table token.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # Verify session exists and is open
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status == "OPEN",
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active or does not exist",
        )

    # Get next round number for this session
    max_round = db.scalar(
        select(func.max(Round.round_number))
        .where(Round.table_session_id == session_id)
    ) or 0
    next_round_number = max_round + 1

    # Create the round
    new_round = Round(
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_session_id=session_id,
        round_number=next_round_number,
        status="SUBMITTED",
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(new_round)
    db.flush()  # Get the round ID

    # Create round items
    for item in body.items:
        # Get product and branch pricing
        result = db.execute(
            select(Product, BranchProduct)
            .join(BranchProduct, Product.id == BranchProduct.product_id)
            .where(
                Product.id == item.product_id,
                BranchProduct.branch_id == branch_id,
                BranchProduct.is_available == True,
            )
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {item.product_id} not available in this branch",
            )

        product, branch_product = result

        round_item = RoundItem(
            tenant_id=tenant_id,
            branch_id=branch_id,
            round_id=new_round.id,
            product_id=product.id,
            qty=item.qty,
            unit_price_cents=branch_product.price_cents,
            notes=item.notes,
        )
        db.add(round_item)

    db.commit()
    db.refresh(new_round)

    # Publish event to Redis
    redis = None
    try:
        redis = await get_redis_client()
        await publish_round_event(
            redis_client=redis,
            event_type=ROUND_SUBMITTED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            table_id=table_id,
            session_id=session_id,
            round_id=new_round.id,
            round_number=next_round_number,
            actor_user_id=None,
            actor_role="DINER",
        )
    except Exception as e:
        # Log but don't fail the request if Redis is unavailable
        logger.error("Failed to publish ROUND_SUBMITTED event", round_id=new_round.id, session_id=session_id, error=str(e))
    finally:
        if redis:
            await redis.close()

    return SubmitRoundResponse(
        session_id=session_id,
        round_id=new_round.id,
        round_number=next_round_number,
        status=new_round.status,
    )


@router.get("/session/{session_id}/rounds", response_model=list[RoundOutput])
def get_session_rounds(
    session_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> list[RoundOutput]:
    """
    Get all rounds for a session.

    Returns the history of orders with their current status.
    """
    # Verify session matches token
    if table_ctx["session_id"] != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not match token",
        )

    rounds = db.execute(
        select(Round)
        .where(Round.table_session_id == session_id)
        .order_by(Round.round_number)
    ).scalars().all()

    result = []
    for round_obj in rounds:
        # Get items for this round
        items = db.execute(
            select(RoundItem, Product)
            .join(Product, RoundItem.product_id == Product.id)
            .where(RoundItem.round_id == round_obj.id)
        ).all()

        item_outputs = [
            RoundItemOutput(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name,
                qty=item.qty,
                unit_price_cents=item.unit_price_cents,
                notes=item.notes,
            )
            for item, product in items
        ]

        result.append(
            RoundOutput(
                id=round_obj.id,
                round_number=round_obj.round_number,
                status=round_obj.status,
                items=item_outputs,
                created_at=round_obj.created_at,
            )
        )

    return result


@router.post("/service-call", response_model=ServiceCallOutput)
async def create_service_call(
    body: CreateServiceCallRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> ServiceCallOutput:
    """
    Create a service call (call waiter or request payment help).

    Publishes a SERVICE_CALL_CREATED event for waiters.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # Verify session is active
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active",
        )

    # Check for existing open call of the same type
    existing_call = db.scalar(
        select(ServiceCall).where(
            ServiceCall.table_session_id == session_id,
            ServiceCall.type == body.type,
            ServiceCall.status == "OPEN",
        )
    )

    if existing_call:
        # Return existing call instead of creating duplicate
        return ServiceCallOutput(
            id=existing_call.id,
            type=existing_call.type,
            status=existing_call.status,
            created_at=existing_call.created_at,
            acked_by_user_id=existing_call.acked_by_user_id,
        )

    # Create new service call
    service_call = ServiceCall(
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_session_id=session_id,
        type=body.type,
        status="OPEN",
    )
    db.add(service_call)
    db.commit()
    db.refresh(service_call)

    # PWAW-C003/C004: Publish event using publish_service_call_event with correct entity structure
    redis = None
    try:
        redis = await get_redis_client()
        await publish_service_call_event(
            redis_client=redis,
            event_type=SERVICE_CALL_CREATED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            table_id=table_id,
            session_id=session_id,
            call_id=service_call.id,
            call_type=body.type,
            actor_user_id=None,
            actor_role="DINER",
        )
        logger.info("SERVICE_CALL_CREATED published", call_id=service_call.id, call_type=body.type)
    except Exception as e:
        logger.error("Failed to publish SERVICE_CALL_CREATED event", service_call_id=service_call.id, error=str(e))
    finally:
        if redis:
            await redis.close()

    return ServiceCallOutput(
        id=service_call.id,
        type=service_call.type,
        status=service_call.status,
        created_at=service_call.created_at,
        acked_by_user_id=service_call.acked_by_user_id,
        session_id=session_id,
    )


@router.get("/session/{session_id}/total")
def get_session_total(
    session_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> dict[str, Any]:
    """
    Get the total amount for a session.

    Calculates total from all rounds (excluding CANCELED).
    """
    if table_ctx["session_id"] != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not match token",
        )

    # Calculate total from all round items
    total_cents = db.scalar(
        select(func.sum(RoundItem.unit_price_cents * RoundItem.qty))
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id == session_id,
            Round.status != "CANCELED",
        )
    ) or 0

    # Check if there's an active check
    check = db.scalar(
        select(Check)
        .where(Check.table_session_id == session_id)
        .order_by(Check.created_at.desc())
    )

    return {
        "session_id": session_id,
        "total_cents": total_cents,
        "paid_cents": check.paid_cents if check else 0,
        "check_id": check.id if check else None,
        "check_status": check.status if check else None,
    }


@router.get("/check", response_model=CheckDetailOutput)
def get_diner_check(
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> CheckDetailOutput:
    """
    Get the current check detail for the diner's session.

    Returns full breakdown of items and payments.
    Used by diner to see their bill before/during payment.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]

    # Get the check for this session
    check = db.scalar(
        select(Check)
        .where(Check.table_session_id == session_id)
        .order_by(Check.created_at.desc())
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check found for this session. Request check first.",
        )

    # Get table code
    table = db.scalar(select(Table).where(Table.id == table_id))

    # Get all items from all rounds (non-canceled)
    items_query = db.execute(
        select(RoundItem, Product, Round.round_number)
        .join(Product, RoundItem.product_id == Product.id)
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id == session_id,
            Round.status != "CANCELED",
        )
        .order_by(Round.round_number, RoundItem.id)
    ).all()

    items = [
        CheckItemOutput(
            product_name=product.name,
            qty=item.qty,
            unit_price_cents=item.unit_price_cents,
            subtotal_cents=item.qty * item.unit_price_cents,
            notes=item.notes,
            round_number=round_number,
        )
        for item, product, round_number in items_query
    ]

    # Get payments
    payments = db.execute(
        select(Payment)
        .where(Payment.check_id == check.id)
        .order_by(Payment.created_at)
    ).scalars().all()

    payment_outputs = [
        PaymentOutput(
            id=p.id,
            provider=p.provider,
            status=p.status,
            amount_cents=p.amount_cents,
            created_at=p.created_at,
        )
        for p in payments
    ]

    return CheckDetailOutput(
        id=check.id,
        status=check.status,
        total_cents=check.total_cents,
        paid_cents=check.paid_cents,
        remaining_cents=max(0, check.total_cents - check.paid_cents),
        items=items,
        payments=payment_outputs,
        created_at=check.created_at,
        table_code=table.code if table else None,
    )
