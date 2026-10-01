"""Approving or rejecting a claim, in both stages. Checks it is the person's turn, records it, then passes the claim on or finishes the stage."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.db import utc_now
from src.database.models import Approval, Category, Claim, Employee
from src.errors import AppError
from src.notifications.notifications import Notifications
from src.policy.policy import Policy
from src.pydantic_models.approval import ApproveOut, PendingApprovalOut, RejectOut
from src.pydantic_models.claim import ApproverOut

# Which approvals are running for a claim in each status. A claim in any other status has nothing to decide.
PHASE_BY_STATUS = {"pending_approval": "request", "awaiting_advance": "request", "settlement_review": "settlement"}


class Approvals:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = Notifications(db)
        self.policy = Policy(db)

    # ---------- the two decisions ----------

    def approve(self, user: Employee, claim_no: str) -> ApproveOut:
        """Record `user`'s approval, then move the claim on. Everything is saved together at the end."""
        claim = self._get_claim(claim_no)
        step = self._my_turn(claim, user)
        step.decision, step.decided_at = "approved", utc_now()
        employee = self.db.get(Employee, claim.employee_code)
        if step.action not in ("release_advance", "release_payment"):  # those two get their own, more useful message when finished
            self.notifications.send(employee.emp_code, claim_no, f"{user.name} ({step.role}) approved your claim.")

        following = self._first_pending(claim_no, step.phase)
        if following is not None:
            self._hand_over(claim, employee, following)
        elif step.phase == "request":
            self._finish_request(claim, employee, step)
        else:
            self._finish_settlement(claim, employee)
        self.db.commit()
        return ApproveOut(claim_no=claim_no, status=claim.status, next_approver=self._as_approver(following))

    def reject(self, user: Employee, claim_no: str, remarks: str) -> RejectOut:
        """Reject the claim as `user`. Same rules as approving (it must be their turn), but this ends the claim for good."""
        claim = self._get_claim(claim_no)
        step = self._my_turn(claim, user)
        step.decision, step.remarks, step.decided_at = "rejected", remarks, utc_now()
        claim.status = "rejected"
        self.notifications.send(claim.employee_code, claim_no, f"{user.name} ({step.role}) rejected your claim: {remarks}")
        self.db.commit()
        return RejectOut(claim_no=claim_no, status=claim.status)

    # ---------- the queue ----------

    def pending_for(self, user: Employee) -> list[PendingApprovalOut]:
        """The claims waiting on `user` right now: their own undecided step, in a stage that is running, with every earlier step done.

        This is exactly the test approve() applies, so anything listed here can be approved, and anything not listed cannot.
        """
        query = (select(Approval, Claim, Category.name, Employee.name)
                 .join(Claim, Claim.claim_no == Approval.claim_no).join(Category, Category.id == Claim.category_id)
                 .join(Employee, Employee.emp_code == Claim.employee_code)
                 .where(Approval.approver_code == user.emp_code, Approval.decision == "pending", Claim.employee_code != user.emp_code)
                 .order_by(Approval.id))
        waiting = []
        for step, claim, template_name, claimant_name in self.db.execute(query):
            if PHASE_BY_STATUS.get(claim.status) != step.phase or self._first_pending(claim.claim_no, step.phase).id != step.id:
                continue  # that stage is over (e.g. rejected), or an earlier approver has not acted yet
            waiting.append(PendingApprovalOut(
                claim_no=claim.claim_no, claimant_code=claim.employee_code, claimant_name=claimant_name, template_name=template_name,
                level=claim.level, status=claim.status, estimated_amount=claim.estimated_amount, advance_requested=self._advance(claim),
                phase=step.phase, role=step.role, action=step.action, created_at=claim.created_at,
            ))
        return waiting

    # ---------- checks ----------

    def _get_claim(self, claim_no: str) -> Claim:
        """The claim, or a 404."""
        claim = self.db.get(Claim, claim_no)
        if claim is None:
            raise AppError(404, "Claim not found")
        return claim

    def _first_pending(self, claim_no: str, phase: str) -> Approval | None:
        """The step that is next in line: the lowest-numbered step of this stage that nobody has decided yet."""
        query = (select(Approval).where(Approval.claim_no == claim_no, Approval.phase == phase, Approval.decision == "pending")
                 .order_by(Approval.step))
        return self.db.scalars(query).first()

    def _my_turn(self, claim: Claim, user: Employee) -> Approval:
        """The user's own pending step, if they may act on it now (approve or reject). Otherwise explains why not."""
        if claim.employee_code == user.emp_code:
            raise AppError(403, "You cannot act on your own claim")
        phase = PHASE_BY_STATUS.get(claim.status)
        if phase is None:
            raise AppError(409, f"This claim is '{claim.status}', there is nothing to decide")
        mine = self.db.scalars(
            select(Approval).where(Approval.claim_no == claim.claim_no, Approval.phase == phase,
                                   Approval.decision == "pending", Approval.approver_code == user.emp_code)
        ).first()
        if mine is None:
            raise AppError(403, "No approval is waiting on you for this claim")
        if mine.id != self._first_pending(claim.claim_no, phase).id:
            raise AppError(409, "An earlier approver has not approved yet")
        return mine

    # ---------- what happens next ----------

    def _hand_over(self, claim: Claim, employee: Employee, following: Approval) -> None:
        """Tell the next person it is their turn, with a message that fits their step."""
        who = f"{employee.name} ({employee.emp_code})"
        if following.action == "release_advance":
            claim.status = "awaiting_advance"  # every approver is done; only Finance's release is left
            message = f"All approvals are done. Please release the advance of INR {self._advance(claim):,.2f} to {who}."
        elif following.action == "verify":
            message = f"{who}'s settlement is ready. Please verify it."
        elif following.action == "release_payment":
            message = f"{who}'s settlement is verified. {self._payout_text(claim)} Please release it."
        else:
            message = f"{who} requests approval for INR {claim.estimated_amount:,.2f} (level L{claim.level})."
        self.notifications.send(following.approver_code, claim.claim_no, message)

    def _finish_request(self, claim: Claim, employee: Employee, last_step: Approval) -> None:
        """Nobody is left in the request stage. If the last step was Finance releasing the advance, record the money."""
        claim.status = "awaiting_settlement"
        note = ""
        if last_step.action == "release_advance":
            claim.advance_amount = self._advance(claim)
            note = f" The advance of INR {claim.advance_amount:,.2f} has been released."
        self.notifications.send(employee.emp_code, claim.claim_no,
                                f"Your claim is fully approved.{note} After the trip, upload your bills and receipts to settle.")

    def _finish_settlement(self, claim: Claim, employee: Employee) -> None:
        """The Controller released the payout: close the claim and tell the employee what happens to the money."""
        totals = self.policy.totals(claim.claim_no, claim.advance_amount)
        claim.status = "paid"
        claim.payment_date = self.policy.next_payment_date(utc_now().date())
        if totals["payable"] > 0:
            message = f"INR {totals['payable']:,.2f} has been dispatched to you. It will be paid in the payment run on {claim.payment_date:%d %b %Y}."
        elif totals["recoverable"] > 0:
            message = (f"Your claim is INR {totals['recoverable']:,.2f} below the advance you took, so that amount will be deducted "
                       "from your next payroll. Nothing is payable to you.")
        else:
            message = "Your claim exactly matches your advance. Nothing more is due."
        self.notifications.send(employee.emp_code, claim.claim_no, message)

    def _payout_text(self, claim: Claim) -> str:
        """One sentence on what the payout is, for the Controller."""
        totals = self.policy.totals(claim.claim_no, claim.advance_amount)
        if totals["payable"] > 0:
            return f"INR {totals['payable']:,.2f} is payable to the employee."
        if totals["recoverable"] > 0:
            return f"Nothing is payable; INR {totals['recoverable']:,.2f} is to be recovered from payroll."
        return "Nothing is payable or recoverable."

    def _advance(self, claim: Claim) -> Decimal:
        """The advance the employee asked for (already checked against the 60% cap when the claim was raised)."""
        return Decimal(str(claim.details.get("advance_requested", 0)))

    def _as_approver(self, step: Approval | None) -> ApproverOut | None:
        """A step as the small {emp_code, name, role} shape the API returns."""
        if step is None:
            return None
        person = self.db.get(Employee, step.approver_code)
        return ApproverOut(emp_code=person.emp_code, name=person.name, role=step.role)
