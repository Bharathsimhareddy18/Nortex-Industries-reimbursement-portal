"""Admin: read-only views of everything. Every endpoint here needs the Admin role.

Templates are not repeated here: the admin uses the same /get_templates and /get_template_required_fields as everyone.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import require_role
from src.admin.admin import Admin
from src.database.db import get_db
from src.pydantic_models.admin import AdminApprovalOut, AdminClaimOut, AdminNotificationOut
from src.pydantic_models.employee import EmployeeOut

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("Admin"))])


@router.get("/users", response_model=list[EmployeeOut])
def all_users(db: Session = Depends(get_db)):
    """Every employee: who they are, their role, and who they report to."""
    return Admin(db).users()


@router.get("/claims", response_model=list[AdminClaimOut])
def all_claims(db: Session = Depends(get_db)):
    """Every claim of every employee, newest first."""
    return Admin(db).claims()


@router.get("/approvals", response_model=list[AdminApprovalOut])
def all_approvals(db: Session = Depends(get_db)):
    """Every approval step of every claim, with who it was assigned to and what they decided."""
    return Admin(db).approvals()


@router.get("/notifications", response_model=list[AdminNotificationOut])
def all_notifications(db: Session = Depends(get_db)):
    """Every notification sent to anyone, newest first."""
    return Admin(db).notifications()
