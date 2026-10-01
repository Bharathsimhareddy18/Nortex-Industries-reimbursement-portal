"""Raising a claim: validate, pick the level, find the approvers, save, notify."""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database.models import Approval, Category, Claim, Employee, Line
from src.errors import AppError
from src.notifications.notifications import Notifications
from src.policy.policy import Policy
from src.pydantic_models.claim import ClaimDetailOut, DetailApprovalOut, DetailReceiptOut, DetailTotalsOut
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

    def list_mine(self, user: Employee) -> list[tuple[Claim, str]]:
        """Every claim this employee raised, newest first, each with its template's name."""
        query = (select(Claim, Category.name).join(Category, Category.id == Claim.category_id)
                 .where(Claim.employee_code == user.emp_code).order_by(Claim.created_at.desc(), Claim.claim_no.desc()))
        return [(claim, name) for claim, name in self.db.execute(query)]

    def _visible_claim(self, user: Employee, claim_no: str) -> Claim:
        """The claim, if it exists and `user` may see it: its owner, or someone on its approval list."""
        claim = self.db.get(Claim, claim_no)
        if claim is None:
            raise AppError(404, "Claim not found")
        approvers = self.db.scalars(select(Approval.approver_code).where(Approval.claim_no == claim_no))
        if user.emp_code != claim.employee_code and user.emp_code not in set(approvers):
            raise AppError(403, "You are not involved in this claim")
        return claim

    def get_status(self, user: Employee, claim_no: str) -> str:
        """Just the claim's current status."""
        return self._visible_claim(user, claim_no).status

    def get_detail(self, user: Employee, claim_no: str) -> ClaimDetailOut:
        """The whole claim for its page: form answers, every approval step, every receipt, and the totals once it is submitted."""
        claim = self._visible_claim(user, claim_no)
        steps = self.db.execute(
            select(Approval, Employee.name).join(Employee, Employee.emp_code == Approval.approver_code)
            .where(Approval.claim_no == claim_no).order_by(Approval.phase, Approval.step)  # 'request' sorts before 'settlement'
        ).all()
        lines = self.db.scalars(select(Line).where(Line.claim_no == claim_no).order_by(Line.id)).all()
        return ClaimDetailOut(
            claim_no=claim_no, claimant_code=claim.employee_code, claimant_name=self.db.get(Employee, claim.employee_code).name,
            template_name=self.db.get(Category, claim.category_id).name, status=claim.status, level=claim.level,
            estimated_amount=claim.estimated_amount, advance_requested=Decimal(str(claim.details.get("advance_requested", 0))).quantize(Decimal("0.01")),
            advance_amount=claim.advance_amount, created_at=claim.created_at, fields=claim.details,
            approvals=[DetailApprovalOut(name=name, role=a.role, phase=a.phase, step=a.step, action=a.action, decision=a.decision,
                                         remarks=a.remarks, decided_at=a.decided_at) for a, name in steps],
            receipts=[self._receipt(line) for line in lines],
            totals=self._totals(claim) if any(a.phase == "settlement" for a, _ in steps) else None,
        )

    def _receipt(self, line: Line) -> DetailReceiptOut:
        """One saved line as a receipt. The merchant is what the AI read from the image."""
        merchant = ((line.extracted or {}).get("receipt") or {}).get("merchant") or line.description
        return DetailReceiptOut(
            line_id=line.id, head=line.head, status=line.status, message=self.policy.receipt_message(line.status, line.reason),
            merchant=merchant, bill_no=line.proof_ref, bill_date=line.line_date, amount=line.amount, paid_by=line.paid_by,
        )

    def _totals(self, claim: Claim) -> DetailTotalsOut:
        """The settlement summary: what the employee paid, the advance, and what is payable or recoverable."""
        t = self.policy.totals(claim.claim_no, claim.advance_amount)
        return DetailTotalsOut(paid_by_employee=t["paid_by_employee"], advance=t["advance"], payable=t["payable"], recoverable=t["recoverable"])

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
