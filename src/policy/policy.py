"""Company policy as code: which level a claim is, and who must approve it. Uses the numbers in config/setting.py."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.setting import settings
from src.database.models import Employee
from src.errors import AppError


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
