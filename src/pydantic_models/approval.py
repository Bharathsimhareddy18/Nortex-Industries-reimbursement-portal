"""The approvals table, as the API shows it."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.pydantic_models.base import RowModel
from src.pydantic_models.claim import ApproverOut, ClaimStatus


class ApprovalOut(RowModel):
    id: int
    claim_no: str
    phase: Literal["request", "settlement"]
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
