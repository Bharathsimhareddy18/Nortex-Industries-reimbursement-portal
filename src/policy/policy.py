"""Company policy as code: which level a claim is, and who must approve it. Uses the numbers in config/setting.py."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.setting import settings
from src.database.models import Employee, Line
from src.errors import AppError
from src.pydantic_models.receipt import ReceiptData


class Policy:
    def __init__(self, db: Session):
        self.db = db

    # ---------- which level (L1..L4) ----------

    def get_level(self, amount: Decimal, international: bool) -> int:
        """L1 to L4 from the approval table. Any international trip is the top level, whatever the amount. Up to 25,000 is L1 (inclusive)."""
        bands = settings.approval_bands
        if international:
            return len(bands)
        for number, band in enumerate(bands, start=1):
            if band.up_to is None or amount <= band.up_to:
                return number

    # ---------- who approves ----------

    def get_reporting_manager_code(self, emp_code: str) -> str | None:
        """The emp_code of this person's reporting manager (None for the MD)."""
        return self.db.scalar(select(Employee.reporting_manager_code).where(Employee.emp_code == emp_code))

    def get_approvers(self, employee: Employee, level: int) -> list[tuple[str, Employee]]:
        """The people who must approve a claim of this level, in order, as (role, person).

        Takes the roles of the level (L2 = Reporting Manager + Head of Department, ...), finds the person for each,
        and drops anyone missing, anyone listed twice (first one wins) and the claimant themself (nobody approves their own claim).
        """
        roles = settings.approval_bands[level - 1].approvers
        approvers, taken = [], {employee.emp_code}  # the claimant starts in 'taken', so they can never be added
        for role in roles:
            person = self._find_person(role, employee)
            if person is not None and person.emp_code not in taken:
                approvers.append((role, person))
                taken.add(person.emp_code)
        return approvers

    def _find_person(self, role: str, claimant: Employee) -> Employee | None:
        """Who fills this role for this claimant: the manager by code, the Head of Department of their department, or the one holder of the role."""
        if role == "Reporting Manager":
            code = self.get_reporting_manager_code(claimant.emp_code)
            return self.db.get(Employee, code) if code else None
        query = select(Employee).where(Employee.role == role).order_by(Employee.emp_code)
        if role == "Head of Department":
            query = query.where(Employee.department == claimant.department)
        return self.db.scalars(query).first()

    # ---------- amounts ----------

    def lodging_limit(self, tier: int) -> Decimal:
        """Hotel room limit per night for a city tier (policy 3.1)."""
        return {1: settings.lodging_tier1, 2: settings.lodging_tier2, 3: settings.lodging_tier3}[tier]

    def estimated_amount(self, template_name: str, fields: dict) -> Decimal:
        """The amount that decides the level. Travelling and Food state it; Hotel stay has no cost field, so it is nights x the tier's lodging limit."""
        if template_name == "Travelling":
            return Decimal(str(fields["estimated_trip_cost"]))
        if template_name == "Food":
            return Decimal(str(fields["amount"]))
        return fields["number_of_days"] * self.lodging_limit(fields["city_tier"])

    def check_advance(self, estimated: Decimal, advance: Decimal) -> None:
        """An advance may be at most 60% of the estimate (policy 1.2). Checked when the request is made."""
        cap = estimated * settings.advance_max_pct / 100
        if advance > cap:
            raise AppError(422, f"Advance {advance:,.2f} is above {settings.advance_max_pct}% of the estimate ({cap:,.2f})")

    # ---------- settlement ----------

    def section_of(self, head: str) -> str:
        """Which block of the Settlement Form a head belongs to."""
        return {"Lodging": "Lodging", "Local conveyance": "Transport"}.get(head, "Other")

    def dedupe_key(self, receipt: ReceiptData) -> str:
        """Finance reconciles bills by merchant, bill number, date and amount (policy 5.3); the same four mean the same bill."""
        return f"{receipt.merchant.strip().lower()}|{receipt.bill_no or ''}|{receipt.bill_date}|{receipt.amount:.2f}"

    def totals(self, claim_no: str, advance: Decimal) -> dict:
        """The settlement summary. Only receipts the employee paid for, and that count, are reimbursed; company-paid ones are memo only."""
        lines = self.db.scalars(select(Line).where(Line.claim_no == claim_no, Line.status.in_(("ok", "disallowed")))).all()
        claimed = sum((l.amount for l in lines if l.paid_by == "Employee"), Decimal("0"))
        net = sum((l.allowed for l in lines if l.paid_by == "Employee"), Decimal("0"))
        return {
            "paid_by_employee": claimed, "paid_by_company": sum((l.amount for l in lines if l.paid_by == "Company"), Decimal("0")),
            "net_reimbursable": net, "advance": advance,
            "payable": max(net - advance, Decimal("0")),  # the company pays the employee
            "recoverable": max(advance - net, Decimal("0")),  # the claim is below the advance: the difference is deducted from payroll (policy 1.3)
        }

    def next_payment_date(self, today: date) -> date:
        """Finance pays on fixed days of the month (policy 5.4): the next one on or after today."""
        days = sorted(settings.payment_run_days)
        for day in days:
            if day >= today.day:
                return today.replace(day=day)
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return date(year, month, days[0])
