"""Login and session checking. Dummy auth: one shared demo password, sessions kept in the sessions table."""
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.setting import settings
from src.database.db import utc_now
from src.database.models import Employee, UserSession


class AuthError(Exception):
    """Wrong credentials, or a missing, wrong or expired session."""


class Auth:
    def __init__(self, db: Session):
        self.db = db

    def login(self, email: str, password: str) -> UserSession:
        """Check email + password and open a session. The same error for both mistakes, so nobody can probe which emails exist."""
        employee = self._find_employee(email)  # the employees row for this email, or None; the row holds the emp_code
        if employee is None or not self._password_ok(password):
            raise AuthError("Wrong email or password")
        return self._new_session(employee.emp_code)  # emp_code is read from that row; the user never types it

    def check_session(self, emp_code: str, token: str) -> Employee:
        """Return the employee behind a session, or raise. The token must exist, belong to this emp_code and not be expired."""
        session = self.db.get(UserSession, token)
        if session is None or session.emp_code != emp_code or session.expires_at < utc_now():
            raise AuthError("Invalid or expired session, please log in again")
        return self.db.get(Employee, emp_code)

    def _find_employee(self, email: str) -> Employee | None:
        """Look the person up by email, ignoring case and stray spaces."""
        return self.db.scalar(select(Employee).where(Employee.email == email.strip().lower()))

    def _password_ok(self, password: str) -> bool:
        """Compare with the shared demo password in constant time, so response time reveals nothing."""
        return secrets.compare_digest(password.encode(), settings.demo_password.encode())

    def _new_session(self, emp_code: str) -> UserSession:
        """Save a session with a random, unguessable token that expires after settings.session_hours."""
        session = UserSession(
            token=secrets.token_urlsafe(32), emp_code=emp_code, expires_at=utc_now() + timedelta(hours=settings.session_hours)
        )
        self.db.add(session)
        self.db.commit()
        return session
