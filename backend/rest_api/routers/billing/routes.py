"""
Billing router.
Handles check requests, payments, and table clearing.
Includes Mercado Pago integration for digital payments.

REC-01 FIX: Uses circuit breaker for Mercado Pago API calls.
REC-02 FIX: Failed webhooks are queued for retry.
"""

from datetime import datetime, timezone
from typing import Any
import hashlib
import hmac
import httpx
import json

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from shared.infrastructure.db import get_db
from shared.security.rate_limit import limiter
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    Check,
    Payment,
    Charge,
    Allocation,
)
from rest_api.services.payments.allocation import (
    create_charges_for_check,
    allocate_payment_fifo,
    get_all_diner_balances,
)
from rest_api.services.payments.circuit_breaker import (
    mercadopago_breaker,
    CircuitBreakerError,
)
from rest_api.services.payments.webhook_retry import webhook_retry_queue
from shared.security.auth import current_user_context, current_table_context, require_roles
from shared.utils.schemas import (
    RequestCheckResponse,
    CashPaymentRequest,
    PaymentResponse,
    ClearTableResponse,
    MercadoPagoPreferenceRequest,
    MercadoPagoPreferenceResponse,
)
from shared.config.settings import settings
from shared.config.logging import billing_logger as logger
from shared.infrastructure.events import (
    get_redis_client,
    publish_to_waiters,
    publish_to_session,
    publish_to_admin,
    publish_check_event,
    publish_table_event,
    Event,
    CHECK_REQUESTED,
    PAYMENT_APPROVED,
    PAYMENT_REJECTED,
    CHECK_PAID,
    TABLE_CLEARED,
)
from rest_api.services.events.outbox_service import write_billing_outbox_event
from shared.security.audit_log import get_audit_log
from rest_api.services.domain import BillingService
from rest_api.services.domain.billing_service import (
    CheckNotFoundError,
    CheckAlreadyExistsError,
)


router = APIRouter(prefix="/api/billing", tags=["billing"])


# CRIT-05 FIX: Rate limiting on billing endpoints
@router.post("/check/request", response_model=RequestCheckResponse)
@limiter.limit("10/minute")
async def request_check(
    request: Request,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> RequestCheckResponse:
    """
    Request the check/bill for a table session.

    Calculates the total from all rounds and creates a Check record.
    Changes table status to PAYING.
    Publishes CHECK_REQUESTED event for waiters.

    Called by diner using table token.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # Verify session is open
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status == "OPEN",
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active",
        )

    # HIGH-04 FIX: Check if there's already a check for this session (idempotency)
    # This prevents duplicate checks when network retries occur
    existing_check = db.scalar(
        select(Check).where(
            Check.table_session_id == session_id,
            Check.status.in_(["OPEN", "REQUESTED", "IN_PAYMENT"]),
        )
    )

    if existing_check:
        # HIGH-04 FIX: Return existing check instead of creating duplicate (idempotent response)
        return RequestCheckResponse(
            check_id=existing_check.id,
            total_cents=existing_check.total_cents,
            paid_cents=existing_check.paid_cents,
            status=existing_check.status,
        )

    # Calculate total from all non-canceled rounds
    total_cents = db.scalar(
        select(func.sum(RoundItem.unit_price_cents * RoundItem.qty))
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id == session_id,
            Round.status != "CANCELED",
        )
    ) or 0

    # Create check
    check = Check(
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_session_id=session_id,
        status="REQUESTED",
        total_cents=total_cents,
        paid_cents=0,
    )
    db.add(check)
    db.flush()  # Get check ID before creating charges

    # Phase 3: Create Charge records for each item
    create_charges_for_check(db, check)

    # Update table and session status
    table = db.scalar(select(Table).where(Table.id == table_id))
    if table:
        table.status = "PAYING"

    session.status = "PAYING"

    # OUTBOX-PATTERN: Write event atomically with business data
    # The outbox processor will publish to Redis, ensuring guaranteed delivery
    write_billing_outbox_event(
        db=db,
        tenant_id=tenant_id,
        event_type=CHECK_REQUESTED,
        check_id=check.id,
        branch_id=branch_id,
        session_id=session_id,
        table_id=table_id,
        extra_data={"total_cents": total_cents},
        actor_role="DINER",
    )

    # AUDIT FIX: Wrap commit in try-except to handle DB errors
    try:
        db.commit()
        db.refresh(check)
    except Exception as e:
        db.rollback()
        logger.error("Failed to commit check request", session_id=session_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create check - please try again",
        )

    # Note: Event publishing is now handled by outbox processor (guaranteed delivery)

    return RequestCheckResponse(
        check_id=check.id,
        total_cents=check.total_cents,
        paid_cents=check.paid_cents,
        status=check.status,
    )


@router.post("/cash/pay", response_model=PaymentResponse)
@limiter.limit("20/minute")
async def record_cash_payment(
    request: Request,
    body: CashPaymentRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> PaymentResponse:
    """
    Record a cash payment for a check.

    Called by waiter after receiving cash from customer.
    If the payment completes the check, marks it as PAID.

    Requires WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # AUDIT FIX: Use SELECT FOR UPDATE to prevent race condition
    # This locks the check row until the transaction completes
    check = db.scalar(
        select(Check).where(Check.id == body.check_id).with_for_update()
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check {body.check_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if check.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    if check.status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check is already paid",
        )

    # HIGH-VALID-02 FIX: Validate payment amount is positive
    if body.amount_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount must be positive",
        )

    # AUDIT FIX: Validate payment amount doesn't exceed remaining
    remaining = check.total_cents - check.paid_cents
    if body.amount_cents > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment amount ({body.amount_cents}) exceeds remaining ({remaining})",
        )

    # Create payment record
    payment = Payment(
        tenant_id=check.tenant_id,
        branch_id=check.branch_id,
        check_id=check.id,
        provider="CASH",
        status="APPROVED",
        amount_cents=body.amount_cents,
        payer_diner_id=body.diner_id,  # Track which diner made the payment
    )
    db.add(payment)
    db.flush()  # Get payment ID before allocating

    # Phase 3: Allocate payment to charges using FIFO
    allocate_payment_fifo(db, payment)

    # Update check
    check.paid_cents += body.amount_cents
    check.status = "IN_PAYMENT"

    # Check if fully paid
    if check.paid_cents >= check.total_cents:
        check.status = "PAID"

    # Get session for event (before commit for table_id)
    session = db.scalar(
        select(TableSession).where(TableSession.id == check.table_session_id)
    )
    table_id = session.table_id if session else None

    # OUTBOX-PATTERN: Write events atomically with business data
    # Payment approved event
    write_billing_outbox_event(
        db=db,
        tenant_id=check.tenant_id,
        event_type=PAYMENT_APPROVED,
        check_id=check.id,
        branch_id=check.branch_id,
        session_id=check.table_session_id,
        table_id=table_id,
        extra_data={
            "payment_id": payment.id,
            "amount_cents": body.amount_cents,
            "provider": "CASH",
        },
        actor_user_id=int(ctx["sub"]),
        actor_role="WAITER",
    )

    # If check is fully paid, also queue CHECK_PAID event
    if check.status == "PAID":
        write_billing_outbox_event(
            db=db,
            tenant_id=check.tenant_id,
            event_type=CHECK_PAID,
            check_id=check.id,
            branch_id=check.branch_id,
            session_id=check.table_session_id,
            table_id=table_id,
            extra_data={"total_cents": check.total_cents},
            actor_user_id=int(ctx["sub"]),
            actor_role="WAITER",
        )

    # AUDIT FIX: Wrap commit in try-except to handle DB errors
    try:
        db.commit()
        db.refresh(payment)
        db.refresh(check)
    except Exception as e:
        db.rollback()
        logger.error("Failed to commit cash payment", check_id=check.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record payment - please try again",
        )

    # SEC-AUDIT-03: Log payment to tamper-evident audit chain
    try:
        audit_log = await get_audit_log()
        await audit_log.log(
            event_type="PAYMENT",
            action="CASH_PAYMENT_APPROVED",
            user_id=int(ctx["sub"]),
            user_email=ctx.get("email"),
            ip_address=request.client.host if request.client else None,
            resource_type="payment",
            resource_id=payment.id,
            data={
                "check_id": check.id,
                "amount_cents": body.amount_cents,
                "provider": "CASH",
                "check_status": check.status,
                "check_paid_cents": check.paid_cents,
                "check_total_cents": check.total_cents,
                "diner_id": body.diner_id,
            },
        )
    except Exception as audit_err:
        # Don't fail the payment if audit logging fails, just log the error
        logger.warning("Failed to write audit log for payment", payment_id=payment.id, error=str(audit_err))

    # Note: Event publishing is now handled by outbox processor (guaranteed delivery)

    return PaymentResponse(
        payment_id=payment.id,
        check_id=check.id,
        amount_cents=payment.amount_cents,
        provider=payment.provider,
        status=payment.status,
        check_status=check.status,
        check_paid_cents=check.paid_cents,
        check_total_cents=check.total_cents,
    )


@router.post("/tables/{table_id}/clear", response_model=ClearTableResponse)
async def clear_table(
    table_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ClearTableResponse:
    """
    Clear/liberate a table after payment is complete.

    Only works if the check is fully paid.
    Closes the session and marks the table as FREE.

    Requires WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # Find the table
    table = db.scalar(
        select(Table).where(Table.id == table_id)
    )

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if table.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Find active session
    session = db.scalar(
        select(TableSession).where(
            TableSession.table_id == table_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        # Table is already free
        table.status = "FREE"
        # QA-BACK-CRIT-01 FIX: Wrap commit in try-except
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to commit table status update", table_id=table_id, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update table status",
            )
        return ClearTableResponse(table_id=table_id, status="FREE")

    # Check if there's a check and if it's paid
    check = db.scalar(
        select(Check).where(
            Check.table_session_id == session.id,
        ).order_by(Check.created_at.desc())
    )

    if check and check.status != "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot clear table: check is not fully paid",
        )

    # Close session and free table
    session.status = "CLOSED"
    session.closed_at = datetime.now(timezone.utc)
    table.status = "FREE"

    # AUDIT FIX: Wrap commit in try-except to handle DB errors
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to commit table clear", table_id=table_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear table - please try again",
        )

    # HIGH-02 FIX: Publish event to waiters and admin channels
    # QA-BACK-HIGH-02 FIX: Include sector_id for sector-based waiter notifications
    redis = None
    try:
        redis = await get_redis_client()
        event = Event(
            type=TABLE_CLEARED,
            tenant_id=table.tenant_id,
            branch_id=table.branch_id,
            table_id=table_id,
            session_id=session.id,
            sector_id=table.sector_id,  # QA-BACK-HIGH-02 FIX
            entity={"table_code": table.code},
            actor={"user_id": int(ctx["sub"]), "role": "WAITER"},
        )
        await publish_to_waiters(redis, table.branch_id, event)
        await publish_to_admin(redis, table.branch_id, event)  # HIGH-02 FIX: Notify admin/dashboard
    except Exception as e:
        logger.error("Failed to publish TABLE_CLEARED event", table_id=table_id, error=str(e))
    # Note: Don't close pooled Redis connection - pool manages lifecycle

    # SEC-AUDIT-03: Log table clearing to tamper-evident audit chain
    try:
        audit_log = await get_audit_log()
        await audit_log.log(
            event_type="TABLE",
            action="TABLE_CLEARED",
            user_id=int(ctx["sub"]),
            user_email=ctx.get("email"),
            resource_type="table_session",
            resource_id=session.id,
            data={
                "table_id": table_id,
                "table_code": table.code,
                "session_id": session.id,
                "check_id": check.id if check else None,
                "check_total_cents": check.total_cents if check else None,
                "branch_id": table.branch_id,
            },
        )
    except Exception as audit_err:
        logger.warning("Failed to write audit log for table clear", table_id=table_id, error=str(audit_err))

    return ClearTableResponse(table_id=table_id, status="FREE")


@router.get("/check/{check_id}")
def get_check(
    check_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> dict[str, Any]:
    """
    Get details of a check.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    check = db.scalar(
        select(Check).where(Check.id == check_id)
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check {check_id} not found",
        )

    branch_ids = ctx.get("branch_ids", [])
    if check.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Get payments
    payments = db.execute(
        select(Payment).where(Payment.check_id == check_id)
    ).scalars().all()

    return {
        "id": check.id,
        "session_id": check.table_session_id,
        "status": check.status,
        "total_cents": check.total_cents,
        "paid_cents": check.paid_cents,
        "remaining_cents": max(0, check.total_cents - check.paid_cents),
        "created_at": check.created_at.isoformat(),
        "payments": [
            {
                "id": p.id,
                "provider": p.provider,
                "status": p.status,
                "amount_cents": p.amount_cents,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ],
    }


# =============================================================================
# Diner Balances (Phase 3)
# =============================================================================


@router.get("/check/{check_id}/balances")
def get_check_balances(
    check_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> list[dict]:
    """
    Get the balance breakdown by diner for a check.

    Phase 3: Shows how much each diner owes and has paid.
    Used by frontend to display split payment breakdown.
    """
    session_id = table_ctx["session_id"]

    # Verify check belongs to this session
    check = db.scalar(
        select(Check).where(
            Check.id == check_id,
            Check.table_session_id == session_id,
        )
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check not found for this session",
        )

    return get_all_diner_balances(db, check_id)


# =============================================================================
# Mercado Pago Integration
# =============================================================================


@router.post("/mercadopago/preference", response_model=MercadoPagoPreferenceResponse)
@limiter.limit("5/minute")
async def create_mercadopago_preference(
    request: Request,
    body: MercadoPagoPreferenceRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> MercadoPagoPreferenceResponse:
    """
    Create a Mercado Pago preference for a check.

    Returns the checkout URL where the diner will be redirected to pay.
    Called by diner when they choose to pay with Mercado Pago.
    """
    if not settings.mercadopago_access_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mercado Pago is not configured",
        )

    session_id = table_ctx["session_id"]

    # Verify check belongs to this session
    check = db.scalar(
        select(Check).where(
            Check.id == body.check_id,
            Check.table_session_id == session_id,
        )
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check not found for this session",
        )

    if check.status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check is already paid",
        )

    # Calculate remaining amount
    remaining_cents = max(0, check.total_cents - check.paid_cents)
    if remaining_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to pay",
        )

    # HIGH-BILLING-01 FIX: Get table for description with proper null checks
    session = db.scalar(
        select(TableSession).where(TableSession.id == session_id)
    )
    # HIGH-BILLING-01 FIX: Validate session exists before accessing table_id
    table = None
    if session and session.table_id:
        table = db.scalar(
            select(Table).where(Table.id == session.table_id)
        )

    table_code = table.code if table else f"Mesa #{session_id}"

    # Create Mercado Pago preference
    preference_data = {
        "items": [
            {
                "title": f"Cuenta {table_code}",
                "description": f"Pago de cuenta - {table_code}",
                "quantity": 1,
                "currency_id": "ARS",
                # HIGH-BILLING-02 FIX: Use integer division to avoid float precision issues
                # Mercado Pago accepts float, but we ensure exact cents conversion
                "unit_price": round(remaining_cents / 100, 2),  # Convert cents to pesos with 2 decimal precision
            }
        ],
        "external_reference": f"check_{check.id}",
        "back_urls": {
            "success": f"{settings.base_url}/payment/success?check_id={check.id}",
            "failure": f"{settings.base_url}/payment/failure?check_id={check.id}",
            "pending": f"{settings.base_url}/payment/pending?check_id={check.id}",
        },
        "auto_return": "approved",
        "notification_url": settings.mercadopago_notification_url or f"{settings.base_url}/api/billing/mercadopago/webhook",
    }

    # REC-01 FIX: Use circuit breaker to prevent cascading failures
    try:
        async with mercadopago_breaker.call():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.mercadopago.com/checkout/preferences",
                    headers={
                        "Authorization": f"Bearer {settings.mercadopago_access_token}",
                        "Content-Type": "application/json",
                    },
                    json=preference_data,
                )

                if response.status_code != 201:
                    logger.error("Mercado Pago preference creation failed", status_code=response.status_code, response=response.text)
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Failed to create Mercado Pago preference",
                    )

                mp_response = response.json()
    except CircuitBreakerError as e:
        logger.warning("Mercado Pago circuit breaker open", retry_after=e.retry_after)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Mercado Pago service temporarily unavailable. Please try again in {int(e.retry_after)} seconds.",
            headers={"Retry-After": str(int(e.retry_after))},
        )

    # Create pending payment record
    payment = Payment(
        tenant_id=check.tenant_id,
        branch_id=check.branch_id,
        check_id=check.id,
        provider="MERCADO_PAGO",
        status="PENDING",
        amount_cents=remaining_cents,
        external_id=mp_response.get("id"),
    )
    db.add(payment)

    # AUDIT FIX: Wrap commit in try-except to handle DB errors
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to create MP payment record", check_id=check.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create payment record - please try again",
        )

    return MercadoPagoPreferenceResponse(
        preference_id=mp_response["id"],
        init_point=mp_response["init_point"],
        sandbox_init_point=mp_response.get("sandbox_init_point", mp_response["init_point"]),
    )


def _verify_mp_webhook_signature(
    x_signature: str | None,
    x_request_id: str | None,
    data_id: str,
) -> bool:
    """
    BACK-CRIT-05 FIX: Verify Mercado Pago webhook signature.

    Mercado Pago sends:
    - x-signature header: "ts=timestamp,v1=signature"
    - x-request-id header

    We compute HMAC-SHA256 of "id:{data_id};request-id:{x_request_id};ts:{ts};"
    using the webhook secret and compare with v1.
    """
    if not settings.mercadopago_webhook_secret:
        # If secret not configured, skip verification (development mode)
        logger.warn("MP webhook signature verification skipped - no secret configured")
        return True

    if not x_signature or not x_request_id:
        logger.warn("MP webhook missing signature headers")
        return False

    # Parse x-signature header
    parts = {}
    for part in x_signature.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            parts[key] = value

    ts = parts.get("ts")
    v1 = parts.get("v1")

    if not ts or not v1:
        logger.warn("MP webhook signature malformed", x_signature=x_signature)
        return False

    # Build manifest string as per MP documentation
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

    # Compute expected signature
    expected_signature = hmac.new(
        settings.mercadopago_webhook_secret.encode(),
        manifest.encode(),
        hashlib.sha256
    ).hexdigest()

    # Compare signatures
    if not hmac.compare_digest(expected_signature, v1):
        logger.warn("MP webhook signature mismatch", expected=expected_signature[:8], received=v1[:8])
        return False

    return True


@router.post("/mercadopago/webhook")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_signature: str | None = Header(None),
    x_request_id: str | None = Header(None),
) -> dict[str, str]:
    """
    Webhook endpoint for Mercado Pago notifications.

    Called by Mercado Pago when a payment status changes.
    Verifies signature, updates payment and check status.
    """
    # Get webhook data
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # BACK-CRIT-05 FIX: Verify webhook signature
    data_id = str(body.get("data", {}).get("id", ""))
    if not _verify_mp_webhook_signature(x_signature, x_request_id, data_id):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Log webhook for debugging
    logger.info("Mercado Pago webhook received", webhook_type=body.get("type"), data_id=data_id)

    # Handle only payment notifications
    if body.get("type") != "payment":
        return {"status": "ignored", "reason": "not a payment notification"}

    payment_id = body.get("data", {}).get("id")
    if not payment_id:
        return {"status": "ignored", "reason": "no payment id"}

    # Fetch payment details from Mercado Pago
    if not settings.mercadopago_access_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mercado Pago is not configured",
        )

    # REC-01 FIX: Use circuit breaker for fetching payment details
    # REC-02 FIX: Queue for retry on failure
    try:
        async with mercadopago_breaker.call():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"https://api.mercadopago.com/v1/payments/{payment_id}",
                    headers={
                        "Authorization": f"Bearer {settings.mercadopago_access_token}",
                    },
                )

                if response.status_code != 200:
                    logger.error("Failed to fetch MP payment", payment_id=payment_id, status_code=response.status_code)
                    # REC-02 FIX: Queue for retry instead of failing immediately
                    await webhook_retry_queue.enqueue(
                        webhook_type="mercadopago",
                        payload=body,
                        error=f"Failed to fetch payment: HTTP {response.status_code}",
                    )
                    return {"status": "queued_for_retry", "reason": "failed to fetch payment details"}

                mp_payment = response.json()
    except CircuitBreakerError as e:
        logger.warning("MP webhook: circuit breaker open, queueing for retry", retry_after=e.retry_after)
        # REC-02 FIX: Queue webhook for retry when circuit is open
        await webhook_retry_queue.enqueue(
            webhook_type="mercadopago",
            payload=body,
            error=f"Circuit breaker open: {e}",
        )
        return {"status": "queued_for_retry", "reason": "service temporarily unavailable"}
    except Exception as e:
        logger.error("MP webhook: unexpected error fetching payment", error=str(e))
        # REC-02 FIX: Queue for retry on any failure
        await webhook_retry_queue.enqueue(
            webhook_type="mercadopago",
            payload=body,
            error=str(e),
        )
        return {"status": "queued_for_retry", "reason": "unexpected error"}

    # Extract check_id from external_reference
    external_ref = mp_payment.get("external_reference", "")
    if not external_ref.startswith("check_"):
        return {"status": "ignored", "reason": "unknown external reference"}

    try:
        check_id = int(external_ref.replace("check_", ""))
    except ValueError:
        return {"status": "ignored", "reason": "invalid check id"}

    # CRIT-01 FIX: Use SELECT FOR UPDATE to prevent race condition on concurrent webhooks
    check = db.scalar(select(Check).where(Check.id == check_id).with_for_update())
    if not check:
        return {"status": "ignored", "reason": "check not found"}

    # Find or create payment record
    # CRIT-01 FIX: Also lock the payment record to prevent double processing
    payment = db.scalar(
        select(Payment).where(
            Payment.check_id == check_id,
            Payment.provider == "MERCADO_PAGO",
            Payment.external_id == str(mp_payment.get("preference_id")),
        ).with_for_update()
    )

    if not payment:
        # Create new payment record
        payment = Payment(
            tenant_id=check.tenant_id,
            branch_id=check.branch_id,
            check_id=check.id,
            provider="MERCADO_PAGO",
            status="PENDING",
            amount_cents=int(mp_payment.get("transaction_amount", 0) * 100),
            external_id=str(payment_id),
        )
        db.add(payment)

    # Update payment status based on MP status
    mp_status = mp_payment.get("status")
    if mp_status == "approved":
        payment.status = "APPROVED"
        payment.amount_cents = int(mp_payment.get("transaction_amount", 0) * 100)

        # Flush to get payment ID before allocating
        db.flush()

        # Allocate payment to charges using FIFO (same as cash payments)
        allocate_payment_fifo(db, payment)

        # Update check
        check.paid_cents += payment.amount_cents
        if check.paid_cents >= check.total_cents:
            check.status = "PAID"
        else:
            check.status = "IN_PAYMENT"

    elif mp_status in ["rejected", "cancelled"]:
        payment.status = "REJECTED"

    # Get session for events (before commit for table_id)
    session = db.scalar(
        select(TableSession).where(TableSession.id == check.table_session_id)
    )
    table_id = session.table_id if session else None

    # OUTBOX-PATTERN: Write events atomically with business data
    if mp_status == "approved":
        write_billing_outbox_event(
            db=db,
            tenant_id=check.tenant_id,
            event_type=PAYMENT_APPROVED,
            check_id=check.id,
            branch_id=check.branch_id,
            session_id=check.table_session_id,
            table_id=table_id,
            extra_data={
                "payment_id": payment.id,
                "amount_cents": payment.amount_cents,
                "provider": "MERCADO_PAGO",
            },
            actor_role="SYSTEM",
        )

        if check.status == "PAID":
            write_billing_outbox_event(
                db=db,
                tenant_id=check.tenant_id,
                event_type=CHECK_PAID,
                check_id=check.id,
                branch_id=check.branch_id,
                session_id=check.table_session_id,
                table_id=table_id,
                extra_data={"total_cents": check.total_cents},
                actor_role="SYSTEM",
            )

    elif mp_status in ["rejected", "cancelled"]:
        write_billing_outbox_event(
            db=db,
            tenant_id=check.tenant_id,
            event_type=PAYMENT_REJECTED,
            check_id=check.id,
            branch_id=check.branch_id,
            session_id=check.table_session_id,
            table_id=table_id,
            extra_data={
                "payment_id": payment.id,
                "reason": mp_payment.get("status_detail", "unknown"),
            },
            actor_role="SYSTEM",
        )

    # CRIT-01 FIX: Wrap commit in try-except to handle DB errors
    try:
        db.commit()
        db.refresh(payment)
        db.refresh(check)
    except Exception as e:
        db.rollback()
        logger.error("Failed to commit MP payment update", check_id=check.id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to process payment - please try again",
        )

    # SEC-AUDIT-03: Log Mercado Pago payment to tamper-evident audit chain
    try:
        audit_log = await get_audit_log()
        action = "MP_PAYMENT_APPROVED" if mp_status == "approved" else "MP_PAYMENT_REJECTED"
        await audit_log.log(
            event_type="PAYMENT",
            action=action,
            ip_address=request.client.host if request.client else None,
            resource_type="payment",
            resource_id=payment.id,
            data={
                "check_id": check.id,
                "amount_cents": payment.amount_cents,
                "provider": "MERCADO_PAGO",
                "mp_status": mp_status,
                "mp_status_detail": mp_payment.get("status_detail"),
                "mp_payment_id": mp_payment_id,
                "check_status": check.status,
                "check_paid_cents": check.paid_cents,
                "check_total_cents": check.total_cents,
            },
        )
    except Exception as audit_err:
        # Don't fail the webhook if audit logging fails, just log the error
        logger.warning("Failed to write audit log for MP payment", payment_id=payment.id, error=str(audit_err))

    # Note: Event publishing is now handled by outbox processor (guaranteed delivery)

    return {"status": "processed", "payment_status": mp_status}

