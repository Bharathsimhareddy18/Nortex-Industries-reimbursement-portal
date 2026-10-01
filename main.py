from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi import APIRouter
import uvicorn
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apis.admin_router import router as admin_router
from apis.approval_router import router as approval_router
from apis.dependencies import current_user
from apis.claim_router import router as claim_router
from apis.dashboard_router import router as dashboard_router
from apis.notification_router import router as notification_router
from apis.settlement_router import router as settlement_router
from apis.templates_router import router as templates_router
from apis.user_router import router as user_router
from src.database.db import SessionLocal, create_tables
from src.errors import AppError
from src.seeder.seeder import seed_admin, seed_employees, seed_templates

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """On every start: make sure the tables exist and the employees and templates are loaded. Safe to repeat, and it means a
    fresh checkout (or a fresh Docker container) works with no setup step."""
    create_tables()
    with SessionLocal() as db:
        seed_employees(db)
        seed_admin(db)
        seed_templates(db)
    yield


app = FastAPI(lifespan=lifespan)
# There is no CORS middleware on purpose. The web pages are served by this same app (see the bottom of this file), so the
# browser needs no permission to call the API, and pages from any OTHER website are refused by the browser's default rules.

# Deny by default: every router below requires a valid login (the emp-code and session-token headers) unless it is left out
# of this list on purpose. Only /auth/login (inside user_router, which protects /auth/me itself) and /health are open.
LOGIN_REQUIRED = [Depends(current_user)]
app.include_router(user_router)
app.include_router(dashboard_router, dependencies=LOGIN_REQUIRED)
app.include_router(templates_router, dependencies=LOGIN_REQUIRED)
app.include_router(claim_router, dependencies=LOGIN_REQUIRED)
app.include_router(approval_router, dependencies=LOGIN_REQUIRED)
app.include_router(notification_router, dependencies=LOGIN_REQUIRED)
app.include_router(settlement_router, dependencies=LOGIN_REQUIRED)
app.include_router(admin_router, dependencies=LOGIN_REQUIRED)


@app.exception_handler(AppError)
def app_error_handler(_request, error: AppError):
    """Turn a broken business rule into a JSON error with the right status code."""
    return JSONResponse(status_code=error.status, content={"detail": error.message, "problems": error.details})


@app.exception_handler(RequestValidationError)
def invalid_input_handler(_request, error: RequestValidationError):
    """Give malformed requests the same JSON shape as our other errors: {detail, problems}."""
    problems = [f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in error.errors()]
    return JSONResponse(status_code=422, content={"detail": "Invalid request", "problems": problems})


@app.get("/health")
def read_root():
    return {"Nortex-Industries-reimbursement-portal": "Welcome!",
            "Version": "1.0.0",
            "Description": "This is a reimbursement portal for Nortex Industries."}

# The UI: plain HTML, CSS and JavaScript in the ui/ folder, served at the site root. This must come LAST, so the API routes
# above are matched first and the static files only answer what is left (/, /login.html, /css/..., /js/...).
app.mount("/", StaticFiles(directory=Path(__file__).parent / "ui", html=True), name="ui")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)