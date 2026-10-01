"""The five tables, exactly as in data_model.md."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.db import Base

Money = Numeric(12, 2)  # never float: 1,415.02 + 743.00 must add up exactly


class Employee(Base):
    """A person. reporting_manager_code links people into the chain that decides who approves."""

    __tablename__ = "employees"

    emp_code: Mapped[str] = mapped_column(String(20), primary_key=True)  # NX-4471
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True)  # login identity
    designation: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(50))  # used to find the Head of Department
    cost_centre: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(50))
    reporting_manager_code: Mapped[str | None] = mapped_column(ForeignKey("employees.emp_code"))  # empty for the MD
    role: Mapped[str] = mapped_column(String(30))  # Employee, Reporting Manager, Head of Department, ...
    password_hash: Mapped[str | None] = mapped_column(String(100))  # bcrypt hash, never the password itself


class Category(Base):
    """An expense category such as Domestic travel. config holds that category's rules as JSON."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    config: Mapped[dict] = mapped_column(JSON)


class Claim(Base):
    """One trip. The same row is updated through every stage; claim_no is the Travel Request ID."""

    __tablename__ = "claims"

    claim_no: Mapped[str] = mapped_column(String(20), primary_key=True)  # TRQ-2026-0001
    employee_code: Mapped[str] = mapped_column(ForeignKey("employees.emp_code"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # pending_approval, awaiting_advance, awaiting_settlement, settlement_review, paid, returned, rejected
    status: Mapped[str] = mapped_column(String(25))
    level: Mapped[int]  # L1..L4 of the current phase
    details: Mapped[dict] = mapped_column(JSON)  # the request form answers
    estimated_amount: Mapped[Decimal] = mapped_column(Money)
    advance_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), server_default="0")
    payment_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Line(Base):
    """One row of the Settlement Form, together with its proof."""

    __tablename__ = "lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    claim_no: Mapped[str] = mapped_column(ForeignKey("claims.claim_no"))
    section: Mapped[str] = mapped_column(String(15))  # Lodging / Transport / Other
    head: Mapped[str] = mapped_column(String(40))  # Lodging, Local conveyance, Meals, Business Entertainment, ...
    line_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(300))
    paid_by: Mapped[str] = mapped_column(String(10))  # exactly 'Employee' or 'Company'
    amount: Mapped[Decimal] = mapped_column(Money)  # what the bill says
    allowed: Mapped[Decimal] = mapped_column(Money)  # what policy allows; disallowed = amount - allowed
    reason: Mapped[str | None] = mapped_column(String(300))  # why it was cut, or a note
    proof_ref: Mapped[str | None] = mapped_column(String(100))  # bill / invoice number
    attendees: Mapped[str | None] = mapped_column(Text)  # names + organisation, for business entertainment
    file_path: Mapped[str | None] = mapped_column(String(255))
    extracted: Mapped[dict | None] = mapped_column(JSON)  # raw parsed / AI output
    merchant_category: Mapped[str | None] = mapped_column(String(30))  # restaurant, cab, hotel, fuel, ...
    dedupe_key: Mapped[str | None] = mapped_column(String(200), index=True)  # merchant|bill no|date|amount
    status: Mapped[str] = mapped_column(String(12))  # ok, disallowed, duplicate, excluded


class Approval(Base):
    """One step of a claim's approval chain, in order. Also the audit trail."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    claim_no: Mapped[str] = mapped_column(ForeignKey("claims.claim_no"))
    phase: Mapped[str] = mapped_column(String(12))  # request / settlement
    step: Mapped[int]  # 1, 2, 3... order within the phase
    role: Mapped[str] = mapped_column(String(30))  # the role this step is for
    action: Mapped[str] = mapped_column(String(20))  # approve | release_advance | verify | release_payment
    approver_code: Mapped[str] = mapped_column(ForeignKey("employees.emp_code"))  # the person asked to act
    decision: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    remarks: Mapped[str | None] = mapped_column(String(500))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class Notification(Base):
    """One message in a person's inbox."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipient_code: Mapped[str] = mapped_column(ForeignKey("employees.emp_code"))
    claim_no: Mapped[str | None] = mapped_column(ForeignKey("claims.claim_no"))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
