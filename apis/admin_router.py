"""Admin: read-only views of everything. Every endpoint here needs the Admin role.

Templates are not repeated here: the admin uses the same /get_templates and /get_template_required_fields as everyone.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import require_role
from src.admin.admin import Admin
from src.flows.flows import Flows
from src.database.db import get_db
from src.pydantic_models.admin import AdminApprovalOut, AdminClaimOut, AdminNotificationOut
from src.pydantic_models.employee import EmployeeOut
from src.pydantic_models.flow import AdminTemplateOut, FlowIn

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


@router.get("/templates", response_model=list[AdminTemplateOut])
def all_templates(db: Session = Depends(get_db)):
    """Every template: the three fixed ones with their fields, and the flows an admin built with their steps."""
    return Flows(db).list_templates()


@router.post("/templates", response_model=AdminTemplateOut, status_code=201)
def create_template(body: FlowIn, db: Session = Depends(get_db)):
    """Build a new template as a flow of steps (ask for fields, approve, advance, upload bills, finance review, payout)."""
    return Flows(db).save_template(body)


@router.put("/templates/{template_id}", response_model=AdminTemplateOut)
def change_template(template_id: int, body: FlowIn, db: Session = Depends(get_db)):
    """Replace the flow of a template an admin built. Claims already raised keep the flow they started with."""
    return Flows(db).save_template(body, template_id)
