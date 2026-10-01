"""Login and 'who am I'."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from src.auth.auth import Auth, AuthError
from src.database.db import get_db
from src.database.models import Employee
from src.pydantic_models.auth import LoginIn, LoginOut
from src.pydantic_models.employee import EmployeeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    """Exchange email + password for a signed JWT (returned as session_token). Every other endpoint needs the returned emp_code and token as headers."""
    try:
        employee, token = Auth(db).login(body.email, body.password)
    except AuthError as error:
        raise HTTPException(status_code=401, detail=str(error))
    return LoginOut(emp_code=employee.emp_code, session_token=token)


@router.get("/me", response_model=EmployeeOut)
def me(user: Employee = Depends(current_user)):
    """Who is logged in? The screens use this to learn the user's name and role. Also proves the session headers work."""
    return user
