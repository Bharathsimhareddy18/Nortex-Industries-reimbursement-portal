"""What the dashboard header shows about the logged-in person."""
from src.pydantic_models.base import RowModel
from src.pydantic_models.employee import Role


class DashboardMeOut(RowModel):
    emp_code: str
    email: str
    designation: str | None
    department: str | None
    role: Role
