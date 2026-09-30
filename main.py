from fastapi import FastAPI
from fastapi import APIRouter
import uvicorn

app = FastAPI()


@app.get("/")
def read_root():
    return {"Nortex-Industries-reimbursement-portal": "Welcome!",
            "Version": "1.0.0",
            "Description": "This is a reimbursement portal for Nortex Industries."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)