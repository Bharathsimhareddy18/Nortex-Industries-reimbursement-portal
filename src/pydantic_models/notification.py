"""The notifications table, as the API shows it."""
from datetime import datetime

from src.pydantic_models.base import RowModel


class NotificationOut(RowModel):
    id: int
    claim_no: str | None
    message: str
    is_read: bool
    created_at: datetime
