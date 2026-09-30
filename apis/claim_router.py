"""Claims."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from src.claims.claims import Claims
from src.database.db import get_db
from src.database.models import Employee
from src.pydantic_models.claim import ApproverOut, CreateClaimIn, CreateClaimOut

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
