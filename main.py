from fastapi import FastAPI
from fastapi import APIRouter
import uvicorn
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apis.approval_router import router as approval_router
from apis.claim_router import router as claim_router
from apis.dashboard_router import router as dashboard_router
from apis.notification_router import router as notification_router
from apis.settlement_router import router as settlement_router
from apis.templates_router import router as templates_router
from apis.user_router import router as user_router
from src.errors import AppError

app = FastAPI()
app.include_router(user_router)
app.include_router(dashboard_router)
app.include_router(templates_router)
app.include_router(claim_router)
app.include_router(approval_router)
app.include_router(notification_router)
app.include_router(settlement_router)


@app.exception_handler(AppError)
def app_error_handler(_request, error: AppError):
    """Turn a broken business rule into a JSON error with the right status code."""
    return JSONResponse(status_code=error.status, content={"detail": error.message, "problems": error.details})


@app.exception_handler(RequestValidationError)
def invalid_input_handler(_request, error: RequestValidationError):
    """Give malformed requests the same JSON shape as our other errors: {detail, problems}."""
    problems = [f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in error.errors()]
    return JSONResponse(status_code=422, content={"detail": "Invalid request", "problems": problems})


@app.get("/")
def read_root():
    return {"Nortex-Industries-reimbursement-portal": "Welcome!",
            "Version": "1.0.0",
            "Description": "This is a reimbursement portal for Nortex Industries."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)