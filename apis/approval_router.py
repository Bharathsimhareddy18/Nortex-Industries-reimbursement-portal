"""Approvals."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from src.approvals.approvals import Approvals
from src.database.db import get_db
from src.database.models import Employee
from src.pydantic_models.approval import ApproveIn, ApproveOut, PendingApprovalOut, RejectIn, RejectOut

router = APIRouter(tags=["approvals"])


@router.post("/approve", response_model=ApproveOut)
def approve(body: ApproveIn, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Approve a claim as the logged-in user. Only works when it is their turn; passes the claim to the next approver,
    or to Finance for the advance, or finishes the request stage."""
    return Approvals(db).approve(user, body.claim_no)


@router.post("/reject", response_model=RejectOut)
def reject(body: RejectIn, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Reject a claim as the logged-in user, with a reason. Same rules as approving: only on your turn, never on your own claim.
    The claim is closed and the claimant sees the reason."""
    return Approvals(db).reject(user, body.claim_no, body.remarks)


@router.get("/get_pending_approvals", response_model=list[PendingApprovalOut])
def get_pending_approvals(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """The logged-in user's approval queue: only the claims where it is their turn to act, oldest first. Once they approve or
    reject, a claim leaves the list, so the screen never has to remember what was decided."""
    return Approvals(db).pending_for(user)
