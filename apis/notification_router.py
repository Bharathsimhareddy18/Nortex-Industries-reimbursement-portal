"""Notifications."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from src.database.db import get_db
from src.database.models import Employee
from src.notifications.notifications import Notifications
from src.pydantic_models.notification import NotificationOut

router = APIRouter(tags=["notifications"])


@router.get("/get_all_notifications", response_model=list[NotificationOut])
def get_all_notifications(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """The logged-in user's inbox, newest first: approval requests, approvals of their own claims, advance releases."""
    return Notifications(db).get_all(user.emp_code)
