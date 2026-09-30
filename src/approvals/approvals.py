"""Approving a claim: check it is this person's turn, record it, then pass the claim to the next person or finish the request stage."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.db import utc_now
from src.database.models import Approval, Claim, Employee
from src.errors import AppError
from src.notifications.notifications import Notifications
from src.pydantic_models.approval import ApproveOut, RejectOut
from src.pydantic_models.claim import ApproverOut

OPEN_STATUSES = ("pending_approval", "awaiting_advance")  # the request stage is still running


class Approvals:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = Notifications(db)

    def approve(self, user: Employee, claim_no: str) -> ApproveOut:
        """Record `user`'s approval of the claim, then move the claim on. Everything is saved together at the end."""
        claim = self._get_claim(claim_no)
        step = self._my_turn(claim, user)
        step.decision, step.decided_at = "approved", utc_now()
        employee = self.db.get(Employee, claim.employee_code)
        if step.action != "release_advance":  # the advance release gets its own message in _finish_request
            self.notifications.send(employee.emp_code, claim_no, f"{user.name} ({step.role}) approved your claim.")

        following = self._first_pending(claim_no)
        if following is not None:
            self._hand_over(claim, employee, following)
        else:
            self._finish_request(claim, employee, step)
        self.db.commit()
        return ApproveOut(claim_no=claim_no, status=claim.status, next_approver=self._as_approver(following))

    def reject(self, user: Employee, claim_no: str, remarks: str) -> RejectOut:
        """Reject the claim as `user`. It follows the same rules as approving (it must be their turn), but it ends the claim for good."""
        claim = self._get_claim(claim_no)
        step = self._my_turn(claim, user)
        step.decision, step.remarks, step.decided_at = "rejected", remarks, utc_now()
        claim.status = "rejected"
        self.notifications.send(claim.employee_code, claim_no, f"{user.name} ({step.role}) rejected your claim: {remarks}")
        self.db.commit()
        return RejectOut(claim_no=claim_no, status=claim.status)

    def _get_claim(self, claim_no: str) -> Claim:
        """The claim, or a 404."""
        claim = self.db.get(Claim, claim_no)
        if claim is None:
            raise AppError(404, "Claim not found")
        return claim

    def _first_pending(self, claim_no: str) -> Approval | None:
        """The step that is next in line: the lowest-numbered step of the request stage that nobody has approved yet."""
        query = (select(Approval).where(Approval.claim_no == claim_no, Approval.phase == "request", Approval.decision == "pending")
                 .order_by(Approval.step))
        return self.db.scalars(query).first()

    def _my_turn(self, claim: Claim, user: Employee) -> Approval:
        """The user's own pending step, if they may act on it now (approve or reject). Otherwise explains why not."""
        if claim.employee_code == user.emp_code:
            raise AppError(403, "You cannot act on your own claim")
        if claim.status not in OPEN_STATUSES:
            raise AppError(409, f"This claim is '{claim.status}', there is nothing to decide")
        mine = self.db.scalars(
            select(Approval).where(Approval.claim_no == claim.claim_no, Approval.phase == "request",
                                   Approval.decision == "pending", Approval.approver_code == user.emp_code)
        ).first()
        if mine is None:
            raise AppError(403, "No approval is waiting on you for this claim")
        if mine.id != self._first_pending(claim.claim_no).id:
            raise AppError(409, "An earlier approver has not approved yet")
        return mine

    def _hand_over(self, claim: Claim, employee: Employee, following: Approval) -> None:
        """Tell the next person it is their turn. If that is Finance's advance release, every approver has finished."""
        if following.action == "release_advance":
            claim.status = "awaiting_advance"
            message = (f"All approvals are done. Please release the advance of INR {self._advance(claim):,.2f} "
                       f"to {employee.name} ({employee.emp_code}).")
        else:
            message = (f"{employee.name} ({employee.emp_code}) requests approval for INR {claim.estimated_amount:,.2f} "
                       f"(level L{claim.level}).")
        self.notifications.send(following.approver_code, claim.claim_no, message)

    def _finish_request(self, claim: Claim, employee: Employee, last_step: Approval) -> None:
        """Nobody is left: the request stage is over. If the last step was Finance releasing the advance, record the money."""
        claim.status = "awaiting_settlement"
        note = ""
        if last_step.action == "release_advance":
            claim.advance_amount = self._advance(claim)
            note = f" The advance of INR {claim.advance_amount:,.2f} has been released."
        self.notifications.send(employee.emp_code, claim.claim_no, f"Your claim is fully approved.{note} After the trip, upload your bills and receipts to settle.")

    def _advance(self, claim: Claim) -> Decimal:
        """The advance the employee asked for (already checked against the 60% cap when the claim was raised)."""
        return Decimal(str(claim.details.get("advance_requested", 0)))

    def _as_approver(self, step: Approval | None) -> ApproverOut | None:
        """A step as the small {emp_code, name, role} shape the API returns."""
        if step is None:
            return None
        person = self.db.get(Employee, step.approver_code)
        return ApproverOut(emp_code=person.emp_code, name=person.name, role=step.role)
