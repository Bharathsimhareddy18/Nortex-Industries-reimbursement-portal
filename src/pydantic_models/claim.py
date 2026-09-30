"""The claims and lines tables, as the API shows them."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from src.pydantic_models.base import RowModel

ClaimStatus = Literal["pending_approval", "awaiting_settlement", "settlement_review", "paid", "returned", "rejected"]
LineStatus = Literal["ok", "disallowed", "duplicate", "excluded"]
PaidBy = Literal["Employee", "Company"]  # exactly these two words, the settlement form sums on them


class LineOut(RowModel):
    id: int
    claim_no: str
    section: Literal["Lodging", "Transport", "Other"]
    head: str
    line_date: date | None
    description: str
    paid_by: PaidBy
    amount: Decimal  # what the bill says
    allowed: Decimal  # what policy allows; disallowed = amount - allowed
    reason: str | None
    proof_ref: str | None
    attendees: str | None
    merchant_category: str | None
    status: LineStatus


class ClaimOut(RowModel):
    claim_no: str  # the Travel Request ID
    employee_code: str
    category_id: int
    status: ClaimStatus
    level: int  # L1..L4
    details: dict  # the request form answers
    estimated_amount: Decimal
    advance_amount: Decimal
    payment_date: date | None
    created_at: datetime
