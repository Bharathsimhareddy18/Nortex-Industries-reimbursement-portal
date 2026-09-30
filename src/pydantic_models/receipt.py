"""Receipts: what Gemini reads from an image, and what the settlement endpoints return."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from src.pydantic_models.claim import ApproverOut, ClaimStatus

# What the employee says a receipt is for.
Head = Literal["Lodging", "Meals", "Business Entertainment", "Local conveyance", "Other"]


class ReceiptData(BaseModel):
    """What Gemini must return for one receipt. Its answer is validated against this before we trust any number."""

    merchant: str
    bill_no: str | None = None  # invoice / bill number, the proof reference
    bill_date: date | None = None
    amount: Decimal = Field(gt=0)  # the grand total on the bill
    paid_by: Literal["Employee", "Company"] = "Employee"  # 'Company' only if a company card paid
    description: str = ""  # one line: what was bought
    items: list[str] = []  # names of the items or services


class ReceiptOut(BaseModel):
    line_id: int
    head: Head  # what the employee claimed it was for
    merchant: str
    bill_no: str | None
    bill_date: date | None
    amount: Decimal
    merchant_type: str | None  # what Jev says the bill is from (None for a duplicate)
    matched: bool  # does that fit the claimed head?
    status: Literal["ok", "duplicate", "excluded"]  # ok = counted; duplicate / excluded = kept out
    message: str


class SubmitIn(BaseModel):
    claim_no: str


class SubmitOut(BaseModel):
    claim_no: str
    status: ClaimStatus
    paid_by_employee: Decimal  # total of the counted receipts
    advance: Decimal
    payable: Decimal  # to be paid to the employee
    recoverable: Decimal  # to be deducted from the employee's payroll
    next_approver: ApproverOut  # the first Finance person
