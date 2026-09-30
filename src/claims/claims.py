"""Raising a claim: validate, pick the level, find the approvers, save, notify."""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database.models import Approval, Category, Claim, Employee
from src.notifications.notifications import Notifications
from src.policy.policy import Policy
from src.templates.templates import Templates


class Claims:
    def __init__(self, db: Session):
        self.db = db
        self.templates = Templates(db)
        self.policy = Policy(db)
        self.notifications = Notifications(db)

    def create(self, employee: Employee, template_id: int, fields: dict) -> tuple[Claim, list[tuple[str, Employee]]]:
        """Raise a claim for `employee` and tell the approvers. Each step is one small method below; everything is saved in one go."""
        template = self.templates.get(template_id)
        clean = self.templates.clean_fields(template, fields)
        amount = self.policy.estimated_amount(template.name, clean)
        self.policy.check_advance(amount, Decimal(str(clean.get("advance_requested", 0))))
        level = self.policy.get_level(amount, bool(clean.get("is_international", False)))
        approvers = self.policy.get_approvers(employee, level)
        advance_step = self._advance_step(template, clean)

        claim = self._save_claim(employee, template, clean, amount, level, waiting=bool(approvers or advance_step))
        self._save_approvals(claim, approvers, advance_step)
        # Approval is one after another, so only the first approver hears about it now; each next one is told when the one before approves.
        # Finance is told after the last approver. With no approvers at all, Finance goes first.
        first = approvers[0][1].emp_code if approvers else (advance_step["emp_code"] if advance_step else None)
        if first:
            self._notify(claim, employee, template, first)
        self.db.commit()
        return claim, approvers

    def _advance_step(self, template: Category, clean: dict) -> dict | None:
        """The template's 'Finance releases the advance' step, but only if this claim asks for an advance (no advance = no Finance step)."""
        for step in template.config.get("finance_steps", []):
            if step["action"] != "release_advance":
                continue
            needed_field = step.get("only_if_positive")
            if needed_field is None or Decimal(str(clean.get(needed_field, 0))) > 0:
                return step
        return None

    def _next_claim_no(self) -> str:
        """The next Travel Request ID, e.g. TRQ-2026-0007."""
        count = self.db.scalar(select(func.count()).select_from(Claim))
        return f"TRQ-{date.today().year}-{count + 1:04d}"

    def _save_claim(self, employee: Employee, template: Category, clean: dict, amount: Decimal, level: int, waiting: bool) -> Claim:
        """Insert the claim row. If nobody has to act on the request, it goes straight to the settlement stage."""
        claim = Claim(
            claim_no=self._next_claim_no(), employee_code=employee.emp_code, category_id=template.id,
            status="pending_approval" if waiting else "awaiting_settlement",
            level=level, details=clean, estimated_amount=amount,
        )
        self.db.add(claim)
        self.db.flush()
        return claim

    def _save_approvals(self, claim: Claim, approvers: list[tuple[str, Employee]], advance_step: dict | None) -> None:
        """One approvals row per approver, in order, then the Finance advance step last. The approve/return/reject API will work on these rows."""
        step = 0
        for step, (role, person) in enumerate(approvers, start=1):
            self.db.add(Approval(claim_no=claim.claim_no, phase="request", step=step, role=role, action="approve", approver_code=person.emp_code))
        if advance_step:
            self.db.add(Approval(
                claim_no=claim.claim_no, phase=advance_step["phase"], step=step + 1, role="Finance",
                action=advance_step["action"], approver_code=advance_step["emp_code"],
            ))

    def _notify(self, claim: Claim, employee: Employee, template: Category, recipient_code: str) -> None:
        """Tell one person a claim is waiting for them."""
        self.notifications.send(recipient_code, claim.claim_no,
                                f"{employee.name} ({employee.emp_code}) requests approval for INR {claim.estimated_amount:,.2f} "
                                f"({template.name}, level L{claim.level}).")
