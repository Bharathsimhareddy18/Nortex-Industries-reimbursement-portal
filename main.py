from fastapi import FastAPI
from fastapi import APIRouter
import uvicorn
from fastapi.responses import JSONResponse

from apis.claim_router import router as claim_router
from apis.dashboard_router import router as dashboard_router
from apis.templates_router import router as templates_router
from apis.user_router import router as user_router
from src.errors import AppError

app = FastAPI()
app.include_router(user_router)
app.include_router(dashboard_router)
app.include_router(templates_router)
app.include_router(claim_router)


@app.exception_handler(AppError)
def app_error_handler(_request, error: AppError):
    """Turn a broken business rule into a JSON error with the right status code."""
    return JSONResponse(status_code=error.status, content={"detail": error.message, "problems": error.details})


@app.get("/")
def read_root():
    return {"Nortex-Industries-reimbursement-portal": "Welcome!",
            "Version": "1.0.0",
            "Description": "This is a reimbursement portal for Nortex Industries."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)