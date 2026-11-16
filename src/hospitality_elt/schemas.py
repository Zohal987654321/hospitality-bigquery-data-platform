"""Data contracts for each source entity.

Validation is deliberately *minimum viable*: the fields downstream models depend on
must exist and have the right type. Extra fields are allowed and land in the raw
``payload`` column, so a vendor adding a field never breaks ingestion.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Contract(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------- POS ----------
class PosLineItem(_Contract):
    line_id: str
    product_id: str
    sku: str
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    net_amount: Decimal


class PosTransaction(_Contract):
    transaction_id: str
    location_id: str
    status: Literal["completed", "voided", "refund"]
    opened_at: datetime
    updated_at: datetime
    total_net: Decimal
    total_tax: Decimal
    line_items: list[PosLineItem] = Field(min_length=1)

    @model_validator(mode="after")
    def lines_sum_to_header(self) -> PosTransaction:
        lines = sum((li.net_amount for li in self.line_items), Decimal("0"))
        if abs(lines - self.total_net) > Decimal("0.01"):
            raise ValueError(f"line net {lines} != header total_net {self.total_net}")
        return self


class PosProduct(_Contract):
    product_id: str
    sku: str
    name: str
    category: str
    updated_at: datetime


class PosLocation(_Contract):
    location_id: str
    name: str
    timezone: str
    updated_at: datetime


# ---------- Workforce ----------
class WorkforceEmployee(_Contract):
    employee_id: str  # pseudonymised before validation
    role: str
    employment_type: Literal["full_time", "part_time", "casual"]
    home_location_id: str
    status: Literal["active", "terminated", "on_leave"]
    updated_at: datetime


class WorkforceShift(_Contract):
    shift_id: str
    employee_id: str  # pseudonymised before validation
    location_id: str
    start_at: datetime
    end_at: datetime
    break_minutes: int = Field(ge=0, le=240)
    labour_cost: Decimal = Field(ge=0)
    status: Literal["approved", "pending", "rejected"]
    updated_at: datetime

    @model_validator(mode="after")
    def end_after_start(self) -> WorkforceShift:
        if self.end_at <= self.start_at:
            raise ValueError("shift end_at must be after start_at")
        return self


# ---------- Inventory (SFTP CSV) ----------
class InventoryStockCount(_Contract):
    location_code: str
    sku: str
    counted_on: date
    quantity_on_hand: Decimal
    unit_cost: Decimal = Field(ge=0)
    exported_at: datetime
    source_file: str
