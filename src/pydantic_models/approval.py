"""The approvals table, as the API shows it."""
from datetime import datetime
from typing import Literal

from src.pydantic_models.base import RowModel


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
