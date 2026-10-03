"""The claims and lines tables, as the API shows them."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from src.pydantic_models.base import RowModel
from src.pydantic_models.template import FieldOut

ClaimStatus = Literal["awaiting_input", "pending_approval", "awaiting_advance", "awaiting_settlement", "settlement_review", "paid", "returned", "rejected"]
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


class SubmitStepIn(BaseModel):
    claim_no: str
    fields: dict  # the answers to the form step the claim is waiting on


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


class ClaimStatusOut(BaseModel):
    claim_no: str
    status: ClaimStatus


class MyClaimOut(BaseModel):
    """One row of the "my claims" list."""

    claim_no: str
    template_name: str
    level: int  # L1..L4
    status: ClaimStatus
    estimated_amount: Decimal
    created_at: datetime


class DetailApprovalOut(BaseModel):
    """One step of the claim's approval chain, as shown on the claim page."""

    name: str  # who is asked to act
    role: str
    phase: Literal["request", "settlement", "flow"]
    step: int
    action: Literal["approve", "release_advance", "verify", "release_payment"]
    decision: Literal["pending", "approved", "returned", "rejected"]
    remarks: str | None
    decided_at: datetime | None


class DetailReceiptOut(BaseModel):
    """One uploaded receipt, as shown on the claim page."""

    line_id: int
    head: str
    status: LineStatus
    message: str  # the same sentence upload_receipt returned
    merchant: str
    bill_no: str | None
    bill_date: date | None
    amount: Decimal
    paid_by: PaidBy


class DetailTotalsOut(BaseModel):
    paid_by_employee: Decimal
    advance: Decimal
    payable: Decimal
    recoverable: Decimal


class FlowStepView(BaseModel):
    """One step of a flow as the claim page and the request page draw it."""

    id: str
    type: str
    title: str
    who: str | None = None  # the person who acts on it, when it has one
    state: Literal["done", "current", "pending"]


class FlowViewOut(BaseModel):
    steps: list[FlowStepView]
    form_title: str | None = None  # set while the claim waits for the employee to fill a form step
    form_fields: list[FieldOut] | None = None
    heads: list[str] | None = None  # set while the claim waits for bills: what a bill may be for


class ClaimDetailOut(BaseModel):
    claim_no: str
    claimant_code: str
    claimant_name: str
    template_name: str
    status: ClaimStatus
    level: int
    estimated_amount: Decimal
    advance_requested: Decimal
    advance_amount: Decimal  # what Finance actually released
    created_at: datetime
    fields: dict  # the answers on the request form
    approvals: list[DetailApprovalOut]  # both stages, in order; the settlement steps appear once it is submitted
    receipts: list[DetailReceiptOut]  # oldest first
    totals: DetailTotalsOut | None  # None until the settlement is submitted
    flow: FlowViewOut | None = None  # only for claims raised from an admin-built flow
