"""Claims."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from src.claims.claims import Claims
from src.database.db import get_db
from src.database.models import Employee
from src.flows.flows import Flows
from src.pydantic_models.claim import ApproverOut, ClaimDetailOut, ClaimStatusOut, CreateClaimIn, CreateClaimOut, MyClaimOut, SubmitStepIn

router = APIRouter(tags=["claims"])


@router.post("/create_claim", response_model=CreateClaimOut, status_code=201)
def create_claim(body: CreateClaimIn, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Raise a claim from a template. The claimant is the logged-in user (from the headers), so no emp code goes in the body.

    Works out the level (L1 to L4) from the amount, finds the approvers, saves the claim and notifies them.
    """
    claim, approvers = Claims(db).create(user, body.template_id, body.fields)
    return CreateClaimOut(
        claim_no=claim.claim_no, status=claim.status, level=claim.level, estimated_amount=claim.estimated_amount,
        approvers=[ApproverOut(emp_code=p.emp_code, name=p.name, role=role) for role, p in approvers],
    )


@router.get("/get_claim_status", response_model=ClaimStatusOut)
def get_claim_status(claim_no: str, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Where is this claim now? Lets a screen show the right thing (for example the receipt upload only once the status is
    awaiting_settlement). Only the claim's owner or one of its approvers may ask."""
    return ClaimStatusOut(claim_no=claim_no, status=Claims(db).get_status(user, claim_no))


@router.get("/get_my_claims", response_model=list[MyClaimOut])
def get_my_claims(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """The claims the logged-in employee raised, newest first. Fills the dashboard and the 'My claims' page, so the UI does not
    have to remember claim numbers itself."""
    return [
        MyClaimOut(claim_no=c.claim_no, template_name=name, level=c.level, status=c.status,
                   estimated_amount=c.estimated_amount, created_at=c.created_at)
        for c, name in Claims(db).list_mine(user)
    ]


@router.get("/get_claim", response_model=ClaimDetailOut)
def get_claim(claim_no: str, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Everything the claim page needs in one call: the form answers, every approval step with its decision, every receipt with its
    result, and the settlement totals once it is submitted. Only the owner or someone on the approval list may read it."""
    return Claims(db).get_detail(user, claim_no)


@router.post("/submit_step", response_model=ClaimStatusOut)
def submit_step(body: SubmitStepIn, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Fill in a later form of a claim raised from an admin-built flow (the owner only, and only while the claim waits for that form)."""
    claim = Flows(db).submit_step(user, body.claim_no, body.fields)
    return ClaimStatusOut(claim_no=claim.claim_no, status=claim.status)
