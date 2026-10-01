"""Dashboard data."""
from fastapi import APIRouter, Depends

from apis.dependencies import current_user
from src.database.models import Employee
from src.pydantic_models.dashboard import DashboardMeOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/me", response_model=DashboardMeOut)
def dashboard_me(user: Employee = Depends(current_user)):
    """Who is this dashboard for? Needs the emp-code and session-token headers. The role tells the screen which menus to show."""
    return user
