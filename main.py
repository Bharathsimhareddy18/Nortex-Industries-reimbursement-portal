from fastapi import FastAPI
from fastapi import APIRouter
import uvicorn

from apis.dashboard_router import router as dashboard_router
from apis.user_router import router as user_router

app = FastAPI()
app.include_router(user_router)
app.include_router(dashboard_router)


@app.get("/")
def read_root():
    return {"Nortex-Industries-reimbursement-portal": "Welcome!",
            "Version": "1.0.0",
            "Description": "This is a reimbursement portal for Nortex Industries."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)