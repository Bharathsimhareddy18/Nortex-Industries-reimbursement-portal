"""Login and token checking. Passwords are stored as bcrypt hashes; a login returns a signed JWT."""
from datetime import timedelta

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.setting import settings
from src.database.db import utc_now
from src.database.models import Employee


class AuthError(Exception):
    """Wrong credentials, or a missing, wrong or expired token."""


def hash_password(password: str) -> str:
    """Salted one-way hash for the employees table. bcrypt puts a fresh random salt in each hash, so equal passwords never look equal."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


# Checked when the email is unknown, so "no such email" takes as long as "wrong password" and timing reveals nothing.
_DUMMY_HASH = hash_password("not-a-real-password")


class Auth:
    def __init__(self, db: Session):
        self.db = db

    def login(self, email: str, password: str) -> tuple[Employee, str]:
        """Check email + password and return (the employee, a JWT). The same error for both mistakes, so nobody can probe which emails exist."""
        employee = self._find_employee(email)
        if employee is None or not self._password_ok(password, employee.password_hash or _DUMMY_HASH):
            raise AuthError("Wrong email or password")
        return employee, self._new_token(employee.emp_code)

    def check_session(self, emp_code: str, token: str) -> Employee:
        """Return the employee behind a token, or raise. The signature and expiry must be valid and the token must be for this emp_code."""
        try:
            claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])  # checks signature and expiry
        except jwt.PyJWTError:
            raise AuthError("Invalid or expired session, please log in again")
        employee = self.db.get(Employee, emp_code)
        if claims.get("sub") != emp_code or employee is None:
            raise AuthError("Invalid or expired session, please log in again")
        return employee

    def _find_employee(self, email: str) -> Employee | None:
        """Look the person up by email, ignoring case and stray spaces."""
        return self.db.scalar(select(Employee).where(Employee.email == email.strip().lower()))

    def _password_ok(self, password: str, password_hash: str) -> bool:
        """bcrypt compares in constant time and re-hashes with the salt stored inside the hash."""
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def _new_token(self, emp_code: str) -> str:
        """Sign a JWT whose subject is the emp_code. Nothing is stored: the signature and the expiry (settings.session_hours) are the proof."""
        expires = utc_now() + timedelta(hours=settings.session_hours)
        return jwt.encode({"sub": emp_code, "exp": expires}, settings.jwt_secret, algorithm="HS256")
