"""The claims and lines tables, as the API shows them."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

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


class CreateClaimIn(BaseModel):
    template_id: int
    fields: dict  # the values for that template's required fields (see /get_template_required_fields)


class ApproverOut(BaseModel):
    emp_code: str
    name: str
    role: str  # which approval slot this person fills, e.g. Reporting Manager


class CreateClaimOut(BaseModel):
    claim_no: str
    status: ClaimStatus
    level: int  # 1..4 (L1..L4)
    estimated_amount: Decimal
    approvers: list[ApproverOut]  # in approval order; empty if nobody above the claimant needs to approve
