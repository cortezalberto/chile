"""
Shared Cart Router.
Handles real-time cart synchronization between diners at a table.
Uses table token authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.infrastructure.db import get_db
from shared.security.rate_limit import limiter
from shared.security.auth import current_table_context
from shared.config.logging import diner_logger as logger
from shared.infrastructure.events import (
    get_redis_client,
    CART_ITEM_ADDED,
    CART_ITEM_UPDATED,
    CART_ITEM_REMOVED,
    CART_CLEARED,
    CART_SYNC,
)
from shared.infrastructure.events.domain_publishers import publish_cart_event
from rest_api.models import (
    TableSession,
    CartItem,
    Product,
    BranchProduct,
    Diner,
)


router = APIRouter(prefix="/api/diner/cart", tags=["diner-cart"])


# =============================================================================
# Schemas
# =============================================================================


class AddToCartRequest(BaseModel):
    """Request to add an item to the shared cart."""
    product_id: int
    quantity: int = Field(ge=1, le=99, default=1)
    notes: str | None = Field(default=None, max_length=500)
    diner_id: int | None = Field(default=None, description="Backend diner ID (optional, for multi-diner support)")


class UpdateCartItemRequest(BaseModel):
    """Request to update a cart item."""
    quantity: int = Field(ge=1, le=99)
    notes: str | None = Field(default=None, max_length=500)


class CartItemOutput(BaseModel):
    """Output for a cart item."""
    item_id: int
    product_id: int
    product_name: str
    product_image: str | None
    price_cents: int
    quantity: int
    notes: str | None
    diner_id: int
    diner_name: str
    diner_color: str

    model_config = {"from_attributes": True}


class CartOutput(BaseModel):
    """Output for the full cart."""
    items: list[CartItemOutput]
    version: int


# =============================================================================
# Background Task for Publishing Events
# =============================================================================


async def _bg_publish_cart_event(
    event_type: str,
    tenant_id: int,
    branch_id: int,
    session_id: int,
    entity: dict,
    actor_diner_id: int | None = None,
):
    """Background task to publish cart event."""
    try:
        redis = await get_redis_client()
        await publish_cart_event(
            redis_client=redis,
            event_type=event_type,
            tenant_id=tenant_id,
            branch_id=branch_id,
            session_id=session_id,
            entity=entity,
            actor_diner_id=actor_diner_id,
        )
        logger.info(f"{event_type} published (bg)", session_id=session_id)
    except Exception as e:
        logger.error(f"Failed to publish {event_type} event (bg)", error=str(e))


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/add", response_model=CartItemOutput)
@limiter.limit("30/minute")
def add_to_cart(
    request: Request,
    body: AddToCartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> CartItemOutput:
    """
    Add an item to the shared cart.

    If the same product already exists for this diner, the quantity is updated (UPSERT).
    Publishes CART_ITEM_ADDED or CART_ITEM_UPDATED event to all diners at the table.

    Requires X-Table-Token header.
    """
    session_id = table_ctx["session_id"]
    tenant_id = table_ctx["tenant_id"]
    branch_id = table_ctx["branch_id"]

    # Get session and validate it's open
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is closed or invalid",
        )

    # Validate product exists and is available in this branch
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.branch_products))
        .where(
            Product.id == body.product_id,
            Product.tenant_id == tenant_id,
            Product.is_active.is_(True),
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Get branch price
    branch_product = next(
        (bp for bp in product.branch_products if bp.branch_id == branch_id and bp.is_active),
        None,
    )
    if not branch_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not available in this branch",
        )

    # Get diner (required for cart items)
    # If diner_id is provided, use it; otherwise fall back to most recent diner
    if body.diner_id:
        diner = db.scalar(
            select(Diner).where(
                Diner.id == body.diner_id,
                Diner.session_id == session_id,
                Diner.is_active.is_(True),
            )
        )
        if not diner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid diner_id for this session",
            )
    else:
        # Fallback: get most recent diner (for backward compatibility)
        diner = db.scalar(
            select(Diner).where(
                Diner.session_id == session_id,
                Diner.is_active.is_(True),
            ).order_by(Diner.joined_at.desc())
        )
        if not diner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No diner registered for this session. Please register first.",
            )

    # Check if item already exists (UPSERT)
    existing_item = db.scalar(
        select(CartItem).where(
            CartItem.session_id == session_id,
            CartItem.diner_id == diner.id,
            CartItem.product_id == body.product_id,
            CartItem.is_active.is_(True),
        )
    )

    if existing_item:
        # Update existing item
        existing_item.quantity = body.quantity
        if body.notes is not None:
            existing_item.notes = body.notes
        event_type = CART_ITEM_UPDATED
        cart_item = existing_item
    else:
        # Create new item
        cart_item = CartItem(
            tenant_id=tenant_id,
            branch_id=branch_id,
            session_id=session_id,
            diner_id=diner.id,
            product_id=body.product_id,
            quantity=body.quantity,
            notes=body.notes,
        )
        db.add(cart_item)
        event_type = CART_ITEM_ADDED

    # Increment cart version
    session.cart_version += 1

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(cart_item)
    except Exception as e:
        db.rollback()
        logger.error("Failed to add item to cart", product_id=body.product_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add to cart - please try again",
        )

    # Build output
    output = CartItemOutput(
        item_id=cart_item.id,
        product_id=product.id,
        product_name=product.name,
        product_image=product.image,
        price_cents=branch_product.price_cents,
        quantity=cart_item.quantity,
        notes=cart_item.notes,
        diner_id=diner.id,
        diner_name=diner.name,
        diner_color=diner.color,
    )

    # Publish event in background
    background_tasks.add_task(
        _bg_publish_cart_event,
        event_type=event_type,
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        entity=output.model_dump(),
        actor_diner_id=diner.id,
    )

    return output


@router.patch("/{item_id}", response_model=CartItemOutput)
@limiter.limit("30/minute")
def update_cart_item(
    request: Request,
    item_id: int,
    body: UpdateCartItemRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> CartItemOutput:
    """
    Update a cart item's quantity or notes.

    Only the diner who added the item can update it.
    Publishes CART_ITEM_UPDATED event to all diners at the table.

    Requires X-Table-Token header.
    """
    session_id = table_ctx["session_id"]
    tenant_id = table_ctx["tenant_id"]
    branch_id = table_ctx["branch_id"]

    # Get cart item with product
    cart_item = db.scalar(
        select(CartItem)
        .options(
            selectinload(CartItem.product).selectinload(Product.branch_products),
            selectinload(CartItem.diner),
        )
        .where(
            CartItem.id == item_id,
            CartItem.session_id == session_id,
            CartItem.is_active.is_(True),
        )
    )
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    # Update item
    cart_item.quantity = body.quantity
    if body.notes is not None:
        cart_item.notes = body.notes

    # Increment cart version
    session = db.get(TableSession, session_id)
    if session:
        session.cart_version += 1

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(cart_item)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update cart item", item_id=item_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update cart - please try again",
        )

    # Get branch price
    branch_product = next(
        (bp for bp in cart_item.product.branch_products if bp.branch_id == branch_id and bp.is_active),
        None,
    )
    price_cents = branch_product.price_cents if branch_product else 0

    # Build output
    output = CartItemOutput(
        item_id=cart_item.id,
        product_id=cart_item.product.id,
        product_name=cart_item.product.name,
        product_image=cart_item.product.image,
        price_cents=price_cents,
        quantity=cart_item.quantity,
        notes=cart_item.notes,
        diner_id=cart_item.diner.id,
        diner_name=cart_item.diner.name,
        diner_color=cart_item.diner.color,
    )

    # Publish event in background
    background_tasks.add_task(
        _bg_publish_cart_event,
        event_type=CART_ITEM_UPDATED,
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        entity=output.model_dump(),
        actor_diner_id=cart_item.diner.id,
    )

    return output


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def remove_cart_item(
    request: Request,
    item_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
):
    """
    Remove an item from the cart.

    Only the diner who added the item can remove it.
    Publishes CART_ITEM_REMOVED event to all diners at the table.

    Requires X-Table-Token header.
    """
    session_id = table_ctx["session_id"]
    tenant_id = table_ctx["tenant_id"]
    branch_id = table_ctx["branch_id"]

    # Get cart item
    cart_item = db.scalar(
        select(CartItem)
        .options(selectinload(CartItem.diner))
        .where(
            CartItem.id == item_id,
            CartItem.session_id == session_id,
            CartItem.is_active.is_(True),
        )
    )
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    diner_id = cart_item.diner.id
    product_id = cart_item.product_id

    # Soft delete
    cart_item.is_active = False

    # Increment cart version
    session = db.get(TableSession, session_id)
    if session:
        session.cart_version += 1

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to remove cart item", item_id=item_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove from cart - please try again",
        )

    # Publish event in background
    background_tasks.add_task(
        _bg_publish_cart_event,
        event_type=CART_ITEM_REMOVED,
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        entity={
            "item_id": item_id,
            "product_id": product_id,
            "diner_id": diner_id,
        },
        actor_diner_id=diner_id,
    )


@router.get("", response_model=CartOutput)
@limiter.limit("60/minute")
def get_cart(
    request: Request,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> CartOutput:
    """
    Get the full shared cart for reconnection/sync.

    Returns all active cart items for the session with current version.

    Requires X-Table-Token header.
    """
    session_id = table_ctx["session_id"]
    branch_id = table_ctx["branch_id"]

    # Get session with cart version
    session = db.get(TableSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Get all active cart items
    cart_items = db.scalars(
        select(CartItem)
        .options(
            selectinload(CartItem.product).selectinload(Product.branch_products),
            selectinload(CartItem.diner),
        )
        .where(
            CartItem.session_id == session_id,
            CartItem.is_active.is_(True),
        )
        .order_by(CartItem.created_at)
    ).all()

    # Build output
    items = []
    for item in cart_items:
        branch_product = next(
            (bp for bp in item.product.branch_products if bp.branch_id == branch_id and bp.is_active),
            None,
        )
        price_cents = branch_product.price_cents if branch_product else 0

        items.append(
            CartItemOutput(
                item_id=item.id,
                product_id=item.product.id,
                product_name=item.product.name,
                product_image=item.product.image,
                price_cents=price_cents,
                quantity=item.quantity,
                notes=item.notes,
                diner_id=item.diner.id,
                diner_name=item.diner.name,
                diner_color=item.diner.color,
            )
        )

    return CartOutput(items=items, version=session.cart_version)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def clear_cart(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
):
    """
    Clear all items from the cart.

    Called after round submission to reset the cart.
    Publishes CART_CLEARED event to all diners at the table.

    Requires X-Table-Token header.
    """
    session_id = table_ctx["session_id"]
    tenant_id = table_ctx["tenant_id"]
    branch_id = table_ctx["branch_id"]

    # Soft delete all cart items
    cart_items = db.scalars(
        select(CartItem).where(
            CartItem.session_id == session_id,
            CartItem.is_active.is_(True),
        )
    ).all()

    for item in cart_items:
        item.is_active = False

    # Reset cart version
    session = db.get(TableSession, session_id)
    if session:
        session.cart_version += 1

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to clear cart", session_id=session_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear cart - please try again",
        )

    # Publish event in background
    background_tasks.add_task(
        _bg_publish_cart_event,
        event_type=CART_CLEARED,
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        entity={"cleared": True},
        actor_diner_id=None,
    )
