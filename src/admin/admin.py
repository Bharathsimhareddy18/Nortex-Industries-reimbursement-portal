"""Read-only views of everything, for the admin. Nothing here changes data."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Approval, Category, Claim, Employee, Notification
from src.pydantic_models.admin import AdminApprovalOut, AdminClaimOut, AdminNotificationOut


class Admin:
    def __init__(self, db: Session):
        self.db = db

    def users(self) -> list[Employee]:
        """Every person in the company, with their role and who they report to."""
        return list(self.db.scalars(select(Employee).order_by(Employee.emp_code)))

    def claims(self) -> list[AdminClaimOut]:
        """Every claim of every employee, newest first."""
        query = (select(Claim, Employee.name, Category.name).join(Employee, Employee.emp_code == Claim.employee_code)
                 .join(Category, Category.id == Claim.category_id).order_by(Claim.created_at.desc(), Claim.claim_no.desc()))
        return [AdminClaimOut(claim_no=c.claim_no, claimant_code=c.employee_code, claimant_name=person, template_name=template,
                              level=c.level, status=c.status, estimated_amount=c.estimated_amount, advance_amount=c.advance_amount,
                              created_at=c.created_at) for c, person, template in self.db.execute(query)]

    def approvals(self) -> list[AdminApprovalOut]:
        """Every approval step of every claim, grouped by claim and in order ('request' sorts before 'settlement')."""
        query = (select(Approval, Employee.name).join(Employee, Employee.emp_code == Approval.approver_code)
                 .order_by(Approval.claim_no.desc(), Approval.phase, Approval.step))
        return [AdminApprovalOut(id=a.id, claim_no=a.claim_no, phase=a.phase, step=a.step, role=a.role, action=a.action,
                                 approver_code=a.approver_code, approver_name=person, decision=a.decision, remarks=a.remarks,
                                 decided_at=a.decided_at) for a, person in self.db.execute(query)]

    def notifications(self) -> list[AdminNotificationOut]:
        """Every message sent to anyone, newest first."""
        query = (select(Notification, Employee.name).join(Employee, Employee.emp_code == Notification.recipient_code)
                 .order_by(Notification.id.desc()))
        return [AdminNotificationOut(id=n.id, recipient_code=n.recipient_code, recipient_name=person, claim_no=n.claim_no,
                                     message=n.message, is_read=n.is_read, created_at=n.created_at) for n, person in self.db.execute(query)]
