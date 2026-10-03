"""The approvals table, as the API shows it."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from src.pydantic_models.base import RowModel
from src.pydantic_models.claim import ApproverOut, ClaimStatus


class ApprovalOut(RowModel):
    id: int
    claim_no: str
    phase: Literal["request", "settlement", "flow"]
    step: int  # order within the phase
    role: str
    action: Literal["approve", "release_advance", "verify", "release_payment"]
    approver_code: str
    decision: Literal["pending", "approved", "returned", "rejected"]
    remarks: str | None
    decided_at: datetime | None


class ApproveIn(BaseModel):
    claim_no: str


class ApproveOut(BaseModel):
    claim_no: str
    status: ClaimStatus  # the claim's state after this approval
    next_approver: ApproverOut | None  # who it went to next; None when the request stage is finished


class RejectIn(BaseModel):
    claim_no: str
    remarks: str = Field(min_length=1)  # why; the claimant sees this


class RejectOut(BaseModel):
    claim_no: str
    status: ClaimStatus  # always 'rejected'


class PendingApprovalOut(BaseModel):
    """One claim that is waiting for the logged-in user to act on it."""

    claim_no: str
    claimant_code: str
    claimant_name: str
    template_name: str
    level: int  # L1..L4
    status: ClaimStatus
    estimated_amount: Decimal
    advance_requested: Decimal  # what the claimant asked for, 0 if nothing
    reason: str | None  # what the money is for and why, in the claimant's words
    phase: Literal["request", "settlement", "flow"]
    role: str  # the role this step is for
    action: Literal["approve", "release_advance", "verify", "release_payment"]  # what the user is being asked to do
    created_at: datetime  # when the claim was raised
