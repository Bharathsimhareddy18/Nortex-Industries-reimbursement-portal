"""Shared by every router: who is calling?"""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.auth.auth import Auth, AuthError
from src.database.db import get_db
from src.database.models import Employee
from src.errors import AppError


def current_user(
    emp_code: str | None = Header(None), session_token: str | None = Header(None), db: Session = Depends(get_db)
) -> Employee:
    """Add this to an endpoint to protect it. The caller must send the headers 'emp-code' and 'session-token'.

    Missing or wrong headers are always a 401 (not a 422), so a screen knows to send the user back to the login page.
    """
    try:
        return Auth(db).check_session(emp_code or "", session_token or "")
    except AuthError as error:
        raise HTTPException(status_code=401, detail=str(error))


def require_role(*roles: str):
    """Build a dependency that lets only people with one of these roles through (everyone else gets a 403)."""

    def check(user: Employee = Depends(current_user)) -> Employee:
        if user.role not in roles:
            raise AppError(403, f"Only {' or '.join(roles)} can do this")
        return user

    return check
