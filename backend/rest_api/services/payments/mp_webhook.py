"""
Mercado Pago webhook handler for retry queue.

REC-02 FIX: Handles retrying failed MP webhook processing.

This module provides the handler function that gets called when
a queued MP webhook is ready for retry.
"""

import httpx
from sqlalchemy import select

from shared.infrastructure.db import SessionLocal
from rest_api.models import Check, Payment, TableSession
from .allocation import allocate_payment_fifo
from .circuit_breaker import mercadopago_breaker, CircuitBreakerError
from .webhook_retry import webhook_retry_queue
from shared.config.settings import settings
from shared.config.logging import get_logger
from shared.infrastructure.events import (
    get_redis_client,
    publish_to_waiters,
    publish_to_session,
    Event,
    PAYMENT_APPROVED,
    PAYMENT_REJECTED,
    CHECK_PAID,
)

logger = get_logger(__name__)


async def handle_mp_webhook_retry(payload: dict) -> bool:
    """
    Process a Mercado Pago webhook that was queued for retry.

    Args:
        payload: Original webhook payload

    Returns:
        True if processed successfully, False if should retry again
    """
    # Extract payment ID from payload
    payment_id = payload.get("data", {}).get("id")
    if not payment_id:
        logger.warning("MP retry: no payment id in payload")
        return True  # Don't retry, invalid payload

    if not settings.mercadopago_access_token:
        logger.error("MP retry: access token not configured")
        return False  # Retry later

    # Fetch payment details from Mercado Pago using circuit breaker
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
                    logger.error(
                        "MP retry: failed to fetch payment",
                        payment_id=payment_id,
                        status_code=response.status_code,
                    )
                    return False  # Retry later

                mp_payment = response.json()

    except CircuitBreakerError:
        logger.warning("MP retry: circuit breaker open")
        return False  # Retry later
    except Exception as e:
        logger.error("MP retry: error fetching payment", error=str(e))
        return False  # Retry later

    # Extract check_id from external_reference
    external_ref = mp_payment.get("external_reference", "")
    if not external_ref.startswith("check_"):
        logger.warning("MP retry: unknown external reference", ref=external_ref)
        return True  # Don't retry, invalid reference

    try:
        check_id = int(external_ref.replace("check_", ""))
    except ValueError:
        logger.warning("MP retry: invalid check id in reference")
        return True  # Don't retry, invalid format

    # Process in database transaction
    with SessionLocal() as db:
        # Lock the check for update
        check = db.scalar(
            select(Check).where(Check.id == check_id).with_for_update()
        )
        if not check:
            logger.warning("MP retry: check not found", check_id=check_id)
            return True  # Don't retry, check doesn't exist

        # Find or create payment record
        payment = db.scalar(
            select(Payment).where(
                Payment.check_id == check_id,
                Payment.provider == "MERCADO_PAGO",
                Payment.external_id == str(mp_payment.get("preference_id")),
            ).with_for_update()
        )

        if not payment:
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

        # Update payment status
        mp_status = mp_payment.get("status")
        if mp_status == "approved":
            payment.status = "APPROVED"
            payment.amount_cents = int(mp_payment.get("transaction_amount", 0) * 100)

            db.flush()  # Get payment ID

            # Allocate payment using FIFO
            allocate_payment_fifo(db, payment)

            # Update check
            check.paid_cents += payment.amount_cents
            if check.paid_cents >= check.total_cents:
                check.status = "PAID"
            else:
                check.status = "IN_PAYMENT"

        elif mp_status in ["rejected", "cancelled"]:
            payment.status = "REJECTED"

        try:
            db.commit()
            db.refresh(payment)
            db.refresh(check)
        except Exception as e:
            db.rollback()
            logger.error("MP retry: failed to commit", check_id=check_id, error=str(e))
            return False  # Retry later

        # Get session for events
        session = db.scalar(
            select(TableSession).where(TableSession.id == check.table_session_id)
        )

    # Publish events (outside DB transaction)
    try:
        redis = await get_redis_client()

        if mp_status == "approved":
            event = Event(
                type=PAYMENT_APPROVED,
                tenant_id=check.tenant_id,
                branch_id=check.branch_id,
                table_id=session.table_id if session else None,
                session_id=check.table_session_id,
                entity={
                    "payment_id": payment.id,
                    "check_id": check.id,
                    "amount_cents": payment.amount_cents,
                    "provider": "MERCADO_PAGO",
                    "from_retry": True,
                },
                actor={"user_id": None, "role": "SYSTEM"},
            )
            await publish_to_waiters(redis, check.branch_id, event)
            await publish_to_session(redis, check.table_session_id, event)

            if check.status == "PAID":
                paid_event = Event(
                    type=CHECK_PAID,
                    tenant_id=check.tenant_id,
                    branch_id=check.branch_id,
                    table_id=session.table_id if session else None,
                    session_id=check.table_session_id,
                    entity={"check_id": check.id, "total_cents": check.total_cents},
                    actor={"user_id": None, "role": "SYSTEM"},
                )
                await publish_to_waiters(redis, check.branch_id, paid_event)
                await publish_to_session(redis, check.table_session_id, paid_event)

        elif mp_status in ["rejected", "cancelled"]:
            event = Event(
                type=PAYMENT_REJECTED,
                tenant_id=check.tenant_id,
                branch_id=check.branch_id,
                table_id=session.table_id if session else None,
                session_id=check.table_session_id,
                entity={
                    "payment_id": payment.id,
                    "check_id": check.id,
                    "reason": mp_payment.get("status_detail", "unknown"),
                },
                actor={"user_id": None, "role": "SYSTEM"},
            )
            await publish_to_session(redis, check.table_session_id, event)

    except Exception as e:
        # Log but don't fail - DB update was successful
        logger.error("MP retry: failed to publish events", error=str(e))

    logger.info(
        "MP retry: webhook processed successfully",
        payment_id=payment_id,
        check_id=check_id,
        status=mp_status,
    )
    return True


def register_mp_webhook_handler() -> None:
    """Register the Mercado Pago webhook handler with the retry queue."""
    webhook_retry_queue.register_handler("mercadopago", handle_mp_webhook_retry)
