"""What the admin screens show: every claim, approval and notification in the system, flat and ready for a table."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from src.pydantic_models.claim import ClaimStatus


class AdminClaimOut(BaseModel):
    claim_no: str
    claimant_code: str
    claimant_name: str
    template_name: str
    level: int
    status: ClaimStatus
    estimated_amount: Decimal
    advance_amount: Decimal
    created_at: datetime


class AdminApprovalOut(BaseModel):
    id: int
    claim_no: str
    phase: str
    step: int
    role: str
    action: str
    approver_code: str
    approver_name: str
    decision: str
    remarks: str | None
    decided_at: datetime | None


class AdminNotificationOut(BaseModel):
    id: int
    recipient_code: str
    recipient_name: str
    claim_no: str | None
    message: str
    is_read: bool
    created_at: datetime
