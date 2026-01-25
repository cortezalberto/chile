"""
Customer router.
FASE 4: Handles customer registration, recognition, and preferences.
Customers are identified users who opted-in for personalized experience.

QA-CRIT-02 FIX: Endpoints now accept device_id from X-Device-Id header
instead of requiring it as query parameter. This allows frontend to send
device_id consistently without modifying each API call.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from shared.infrastructure.db import get_db
from rest_api.models import Customer, Diner, RoundItem, Round, Product
from shared.security.auth import current_table_context
from shared.utils.schemas import (
    CustomerRegisterRequest,
    CustomerOutput,
    CustomerUpdateRequest,
    CustomerRecognizeResponse,
    CustomerSuggestionsOutput,
    FavoriteProductOutput,
)
from shared.config.logging import get_logger

logger = get_logger("customer")

router = APIRouter(prefix="/api/customer", tags=["customer"])


def get_device_id_from_header(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id")
) -> str | None:
    """
    QA-CRIT-02 FIX: Extract device_id from X-Device-Id header.
    Returns None if header is not present.
    """
    return x_device_id


def _parse_json_list(json_str: str | None) -> list:
    """Parse JSON array string to list, returning empty list on failure."""
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []


def _customer_to_output(customer: Customer) -> CustomerOutput:
    """Convert Customer model to output schema."""
    return CustomerOutput(
        id=customer.id,
        tenant_id=customer.tenant_id,
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        first_visit_at=customer.first_visit_at,
        last_visit_at=customer.last_visit_at,
        total_visits=customer.total_visits,
        total_spent_cents=customer.total_spent_cents,
        avg_ticket_cents=customer.avg_ticket_cents,
        excluded_allergen_ids=_parse_json_list(customer.excluded_allergen_ids),
        dietary_preferences=_parse_json_list(customer.dietary_preferences),
        excluded_cooking_methods=_parse_json_list(customer.excluded_cooking_methods),
        favorite_product_ids=_parse_json_list(customer.favorite_product_ids),
        segment=customer.segment,
        consent_remember=customer.consent_remember,
        consent_marketing=customer.consent_marketing,
    )


@router.post("/register", response_model=CustomerOutput)
def register_customer(
    body: CustomerRegisterRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> CustomerOutput:
    """
    FASE 4: Register a new customer with opt-in consent.

    Creates a Customer entity and links all previous visits (Diners)
    with the same device_id to this customer.

    If customer already exists for this device, returns existing.
    """
    tenant_id = table_ctx["tenant_id"]

    # RTR-RACE-01 FIX: Check if customer already exists with this device
    # Use with_for_update() to prevent race condition during concurrent registration
    existing_device_ids = db.scalar(
        select(Customer)
        .where(
            Customer.tenant_id == tenant_id,
            Customer.device_ids.contains(body.device_id),
        )
        .with_for_update(skip_locked=True)  # Skip if locked by another transaction
    )

    if existing_device_ids:
        logger.info("Customer already exists for device", device_id=body.device_id)
        return _customer_to_output(existing_device_ids)

    # RTR-RACE-01 FIX: Check for existing customer by phone or email with locking
    if body.phone:
        existing_phone = db.scalar(
            select(Customer)
            .where(
                Customer.tenant_id == tenant_id,
                Customer.phone == body.phone,
            )
            .with_for_update(skip_locked=True)
        )
        if existing_phone:
            # HIGH-COMMIT-01 FIX: Add device_id to existing customer with proper error handling
            device_ids = _parse_json_list(existing_phone.device_ids)
            if body.device_id not in device_ids:
                device_ids.append(body.device_id)
                existing_phone.device_ids = json.dumps(device_ids)
                try:
                    db.commit()
                    db.refresh(existing_phone)
                except Exception as e:
                    db.rollback()
                    logger.error("Failed to add device to customer", error=str(e))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update customer",
                    )
            return _customer_to_output(existing_phone)

    if body.email:
        existing_email = db.scalar(
            select(Customer)
            .where(
                Customer.tenant_id == tenant_id,
                Customer.email == body.email,
            )
            .with_for_update(skip_locked=True)
        )
        if existing_email:
            # HIGH-COMMIT-02 FIX: Add device_id to existing customer with proper error handling
            device_ids = _parse_json_list(existing_email.device_ids)
            if body.device_id not in device_ids:
                device_ids.append(body.device_id)
                existing_email.device_ids = json.dumps(device_ids)
                try:
                    db.commit()
                    db.refresh(existing_email)
                except Exception as e:
                    db.rollback()
                    logger.error("Failed to add device to customer", error=str(e))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update customer",
                    )
            return _customer_to_output(existing_email)

    # Calculate metrics from previous visits
    previous_visits = db.execute(
        select(Diner)
        .where(
            Diner.device_id == body.device_id,
            Diner.tenant_id == tenant_id,
        )
        .order_by(Diner.joined_at)
    ).scalars().all()

    total_visits = len(previous_visits)
    first_visit = previous_visits[0].joined_at if previous_visits else datetime.now(timezone.utc)
    last_visit = previous_visits[-1].joined_at if previous_visits else datetime.now(timezone.utc)

    # QA-CRIT-04 FIX: Calculate total spent with single aggregated query (avoid N+1)
    total_spent = 0
    if previous_visits:
        session_ids = [d.session_id for d in previous_visits]
        total_spent = db.scalar(
            select(func.coalesce(func.sum(RoundItem.unit_price_cents * RoundItem.qty), 0))
            .join(Round, RoundItem.round_id == Round.id)
            .where(
                Round.table_session_id.in_(session_ids),
                Round.status != "CANCELED",
            )
        ) or 0

    avg_ticket = total_spent // total_visits if total_visits > 0 else 0

    # Create new customer
    # QA-CRIT-01 FIX: Include new fields (birthday, ai_personalization)
    new_customer = Customer(
        tenant_id=tenant_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        birthday_month=body.birthday_month,
        birthday_day=body.birthday_day,
        first_visit_at=first_visit,
        last_visit_at=last_visit,
        total_visits=max(1, total_visits),
        total_spent_cents=total_spent,
        avg_ticket_cents=avg_ticket,
        excluded_allergen_ids=json.dumps(body.excluded_allergen_ids) if body.excluded_allergen_ids else None,
        dietary_preferences=json.dumps(body.dietary_preferences) if body.dietary_preferences else None,
        excluded_cooking_methods=json.dumps(body.excluded_cooking_methods) if body.excluded_cooking_methods else None,
        segment="new" if total_visits <= 1 else ("occasional" if total_visits <= 3 else "regular"),
        consent_remember=body.consent_remember,
        consent_marketing=body.consent_marketing,
        ai_personalization_enabled=body.ai_personalization_enabled,
        device_ids=json.dumps([body.device_id]),
    )

    db.add(new_customer)

    try:
        db.commit()
        db.refresh(new_customer)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create customer", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer",
        )

    # RACE-01 FIX: Link previous visits to customer with proper error handling
    # This is separate from customer creation to avoid rolling back the customer
    # if visit linking fails (customer already exists and is valid)
    if previous_visits:
        try:
            for diner in previous_visits:
                diner.customer_id = new_customer.id
            db.commit()
        except Exception as e:
            # Visit linking failed - log but don't fail the registration
            # Customer is already created, visits can be linked later
            db.rollback()
            logger.warning(
                "Failed to link visits to customer (customer created successfully)",
                customer_id=new_customer.id,
                device_id=body.device_id,
                visits_count=len(previous_visits),
                error=str(e),
            )
            # Refresh customer from DB to return valid data
            db.refresh(new_customer)

    logger.info(
        "Customer registered",
        customer_id=new_customer.id,
        device_id=body.device_id,
        visits_linked=len(previous_visits),
    )

    return _customer_to_output(new_customer)


@router.get("/recognize", response_model=CustomerRecognizeResponse)
def recognize_customer(
    device_id: str | None = None,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
    header_device_id: str | None = Depends(get_device_id_from_header),
) -> CustomerRecognizeResponse:
    """
    FASE 4: Check if a device is linked to a known customer.

    Called on app start to determine personalized greeting.
    Also returns whether to prompt for opt-in (after 3+ anonymous visits).

    QA-CRIT-02 FIX: device_id can come from query param OR X-Device-Id header.
    """
    # QA-CRIT-02 FIX: Prefer query param, fallback to header
    effective_device_id = device_id or header_device_id
    if not effective_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id required (query param or X-Device-Id header)",
        )

    tenant_id = table_ctx["tenant_id"]

    # Check for existing customer with this device
    customer = db.scalar(
        select(Customer)
        .where(
            Customer.tenant_id == tenant_id,
            Customer.device_ids.contains(effective_device_id),
        )
    )

    if customer:
        return CustomerRecognizeResponse(
            recognized=True,
            customer_id=customer.id,
            customer_name=customer.name,
            last_visit=customer.last_visit_at,
            visit_count=customer.total_visits,
            should_prompt_optin=False,
            anonymous_visit_count=0,
        )

    # Count anonymous visits for this device
    anonymous_visits = db.scalar(
        select(func.count(Diner.id))
        .where(
            Diner.device_id == effective_device_id,
            Diner.tenant_id == tenant_id,
            Diner.customer_id.is_(None),
        )
    ) or 0

    # Prompt opt-in after 3+ visits
    should_prompt = anonymous_visits >= 3

    return CustomerRecognizeResponse(
        recognized=False,
        should_prompt_optin=should_prompt,
        anonymous_visit_count=anonymous_visits,
    )


@router.get("/me", response_model=CustomerOutput)
def get_current_customer(
    device_id: str | None = None,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
    header_device_id: str | None = Depends(get_device_id_from_header),
) -> CustomerOutput:
    """
    FASE 4: Get profile of customer linked to this device.

    QA-CRIT-02 FIX: device_id can come from query param OR X-Device-Id header.
    """
    # QA-CRIT-02 FIX: Prefer query param, fallback to header
    effective_device_id = device_id or header_device_id
    if not effective_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id required (query param or X-Device-Id header)",
        )

    tenant_id = table_ctx["tenant_id"]

    customer = db.scalar(
        select(Customer)
        .where(
            Customer.tenant_id == tenant_id,
            Customer.device_ids.contains(effective_device_id),
        )
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No customer found for this device",
        )

    return _customer_to_output(customer)


@router.patch("/me", response_model=CustomerOutput)
def update_customer(
    body: CustomerUpdateRequest,
    device_id: str | None = None,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
    header_device_id: str | None = Depends(get_device_id_from_header),
) -> CustomerOutput:
    """
    FASE 4: Update customer preferences.

    QA-CRIT-02 FIX: device_id can come from query param OR X-Device-Id header.
    """
    # QA-CRIT-02 FIX: Prefer query param, fallback to header
    effective_device_id = device_id or header_device_id
    if not effective_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id required (query param or X-Device-Id header)",
        )

    tenant_id = table_ctx["tenant_id"]

    customer = db.scalar(
        select(Customer)
        .where(
            Customer.tenant_id == tenant_id,
            Customer.device_ids.contains(effective_device_id),
        )
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No customer found for this device",
        )

    # Update fields if provided
    if body.name is not None:
        customer.name = body.name
    if body.phone is not None:
        customer.phone = body.phone
    if body.email is not None:
        customer.email = body.email
    if body.excluded_allergen_ids is not None:
        customer.excluded_allergen_ids = json.dumps(body.excluded_allergen_ids)
    if body.dietary_preferences is not None:
        customer.dietary_preferences = json.dumps(body.dietary_preferences)
    if body.excluded_cooking_methods is not None:
        customer.excluded_cooking_methods = json.dumps(body.excluded_cooking_methods)
    if body.consent_marketing is not None:
        customer.consent_marketing = body.consent_marketing

    try:
        db.commit()
        db.refresh(customer)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update customer", customer_id=customer.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer",
        )

    return _customer_to_output(customer)


@router.get("/suggestions", response_model=CustomerSuggestionsOutput)
def get_suggestions(
    device_id: str | None = None,
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
    header_device_id: str | None = Depends(get_device_id_from_header),
) -> CustomerSuggestionsOutput:
    """
    FASE 4: Get personalized product suggestions.

    Returns:
    - favorites: Top 5 most ordered products
    - last_ordered: Products from last visit
    - recommendations: Products similar to favorites (same subcategory, not yet ordered)

    QA-CRIT-02 FIX: device_id can come from query param OR X-Device-Id header.
    """
    # QA-CRIT-02 FIX: Prefer query param, fallback to header
    effective_device_id = device_id or header_device_id
    if not effective_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id required (query param or X-Device-Id header)",
        )

    tenant_id = table_ctx["tenant_id"]
    effective_branch_id = branch_id or table_ctx.get("branch_id")

    # Check for customer
    customer = db.scalar(
        select(Customer)
        .where(
            Customer.tenant_id == tenant_id,
            Customer.device_ids.contains(effective_device_id),
        )
    )

    customer_id = customer.id if customer else None

    # Get all diners for this device
    # QA-CRIT-02 FIX: Use effective_device_id
    diner_ids = db.execute(
        select(Diner.id)
        .where(
            Diner.device_id == effective_device_id,
            Diner.tenant_id == tenant_id,
        )
    ).scalars().all()

    if not diner_ids:
        return CustomerSuggestionsOutput(
            device_id=effective_device_id,
            customer_id=customer_id,
        )

    # Get favorite products (top 5 by order count)
    favorites_query = db.execute(
        select(
            Product.id,
            Product.name,
            Product.image,
            func.sum(RoundItem.qty).label("times_ordered"),
            func.max(Round.submitted_at).label("last_ordered"),
        )
        .join(RoundItem, Product.id == RoundItem.product_id)
        .join(Round, RoundItem.round_id == Round.id)
        .join(Diner, Round.table_session_id == Diner.session_id)
        .where(
            Diner.device_id == effective_device_id,  # QA-CRIT-02 FIX
            Diner.tenant_id == tenant_id,
            Round.status != "CANCELED",
            Product.is_active.is_(True),
        )
        .group_by(Product.id, Product.name, Product.image)
        .order_by(func.sum(RoundItem.qty).desc())
        .limit(5)
    ).all()

    favorites = [
        FavoriteProductOutput(
            id=row.id,
            name=row.name,
            image=row.image,
            times_ordered=row.times_ordered,
            last_ordered=row.last_ordered,
        )
        for row in favorites_query
    ]

    # Get last ordered products (from most recent session)
    # QA-CRIT-02 FIX: Use effective_device_id
    last_session = db.scalar(
        select(Diner)
        .where(
            Diner.device_id == effective_device_id,
            Diner.tenant_id == tenant_id,
        )
        .order_by(Diner.joined_at.desc())
    )

    last_ordered = []
    if last_session:
        last_items = db.execute(
            select(
                Product.id,
                Product.name,
                Product.image,
                func.sum(RoundItem.qty).label("times_ordered"),
            )
            .join(RoundItem, Product.id == RoundItem.product_id)
            .join(Round, RoundItem.round_id == Round.id)
            .where(
                Round.table_session_id == last_session.session_id,
                Round.status != "CANCELED",
                Product.is_active.is_(True),
            )
            .group_by(Product.id, Product.name, Product.image)
            .limit(5)
        ).all()

        last_ordered = [
            FavoriteProductOutput(
                id=row.id,
                name=row.name,
                image=row.image,
                times_ordered=row.times_ordered,
            )
            for row in last_items
        ]

    # Get recommendations (same subcategory as favorites, not yet ordered)
    recommendations = []
    if favorites:
        # Get subcategories of favorite products
        favorite_ids = [f.id for f in favorites]
        favorite_subcategories = db.execute(
            select(Product.subcategory_id)
            .where(
                Product.id.in_(favorite_ids),
                Product.subcategory_id.isnot(None),
            )
            .distinct()
        ).scalars().all()

        if favorite_subcategories:
            # Get ordered product IDs
            # QA-CRIT-02 FIX: Use effective_device_id
            ordered_ids = db.execute(
                select(RoundItem.product_id)
                .join(Round, RoundItem.round_id == Round.id)
                .join(Diner, Round.table_session_id == Diner.session_id)
                .where(
                    Diner.device_id == effective_device_id,
                    Diner.tenant_id == tenant_id,
                )
                .distinct()
            ).scalars().all()

            # Find unordered products in same subcategories
            recs_query = db.execute(
                select(Product.id, Product.name, Product.image)
                .where(
                    Product.subcategory_id.in_(favorite_subcategories),
                    Product.id.notin_(ordered_ids) if ordered_ids else True,
                    Product.is_active.is_(True),
                    Product.tenant_id == tenant_id,
                )
                .limit(5)
            ).all()

            # QA-HIGH-03 FIX: Explicitly set last_ordered=None for recommendations (never ordered)
            recommendations = [
                FavoriteProductOutput(
                    id=row.id,
                    name=row.name,
                    image=row.image,
                    times_ordered=0,
                    last_ordered=None,
                )
                for row in recs_query
            ]

    # Update customer favorites if exists
    if customer and favorites:
        customer.favorite_product_ids = json.dumps([f.id for f in favorites])
        db.commit()

    return CustomerSuggestionsOutput(
        device_id=effective_device_id,  # QA-CRIT-02 FIX
        customer_id=customer_id,
        favorites=favorites,
        last_ordered=last_ordered,
        recommendations=recommendations,
    )
