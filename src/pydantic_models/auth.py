"""Login request and response."""
from pydantic import BaseModel


class LoginIn(BaseModel):
    email: str
    password: str


class LoginOut(BaseModel):
    emp_code: str
    session_token: str  # send this and the emp_code as headers on every later request
