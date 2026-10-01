"""The inbox: every message the system sends to a person goes through here."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Notification


class Notifications:
    def __init__(self, db: Session):
        self.db = db

    def send(self, recipient_code: str, claim_no: str | None, message: str) -> None:
        """Put a message in one person's inbox. The caller commits, so it is saved together with the change that caused it."""
        self.db.add(Notification(recipient_code=recipient_code, claim_no=claim_no, message=message))

    def get_all(self, emp_code: str) -> list[Notification]:
        """Everything in this person's inbox, newest first."""
        query = select(Notification).where(Notification.recipient_code == emp_code).order_by(Notification.id.desc())
        return list(self.db.scalars(query))
