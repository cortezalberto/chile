from datetime import datetime
from typing import Literal, List, Optional
from pydantic import BaseModel, Field

# Station types
StationType = Literal["BAR", "HOT_KITCHEN", "COLD_KITCHEN", "GRILL", "PASTRY", "OTHER"]
TicketStatus = Literal["PENDING", "IN_PROGRESS", "READY", "DELIVERED"]
TicketItemStatus = Literal["PENDING", "IN_PROGRESS", "READY"]

class KitchenTicketItemOutput(BaseModel):
    """Output for a single item in a kitchen ticket."""
    id: int
    round_item_id: int
    product_id: int
    product_name: str
    qty: int
    status: TicketItemStatus
    notes: str | None = None

class KitchenTicketOutput(BaseModel):
    """Output for a kitchen ticket with its items."""
    id: int
    round_id: int
    round_number: int
    station: StationType
    status: TicketStatus
    priority: int
    notes: str | None = None
    table_id: int | None = None
    table_code: str | None = None
    items: List[KitchenTicketItemOutput]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    delivered_at: datetime | None = None

class KitchenTicketsByStation(BaseModel):
    """Tickets grouped by station."""
    station: StationType
    tickets: List[KitchenTicketOutput]

class ListTicketsResponse(BaseModel):
    """Response for listing tickets grouped by station."""
    stations: List[KitchenTicketsByStation]

class UpdateTicketStatusRequest(BaseModel):
    """Request to update ticket status."""
    status: Literal["IN_PROGRESS", "READY", "DELIVERED"]

class GenerateTicketsRequest(BaseModel):
    """Request to generate tickets from a round."""
    station_mapping: dict[int, StationType] | None = Field(
        default=None,
        description="Optional mapping of category_id to station. If not provided, uses default mapping."
    )
    priority: int = Field(default=0, description="Priority for generated tickets (higher = more urgent)")

class GenerateTicketsResponse(BaseModel):
    """Response after generating tickets."""
    round_id: int
    tickets_created: int
    tickets: List[KitchenTicketOutput]
