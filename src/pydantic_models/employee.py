"""The employees table, as the API shows it."""
from typing import Literal

from src.pydantic_models.base import RowModel

Role = Literal["Employee", "Reporting Manager", "Head of Department", "Head of Division", "MD", "Finance", "Admin"]


class EmployeeOut(RowModel):
    emp_code: str
    name: str
    email: str
    designation: str | None
    department: str | None
    cost_centre: str | None
    city: str | None
    reporting_manager_code: str | None  # empty for the MD
    role: Role
