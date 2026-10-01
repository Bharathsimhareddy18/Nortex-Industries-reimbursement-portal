"""Trip settlement."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from apis.dependencies import current_user
from config.setting import settings
from src.database.db import get_db
from src.database.models import Employee
from src.pydantic_models.receipt import Head, ReceiptOut, SubmitIn, SubmitOut
from src.settlement.settlement import Settlement

router = APIRouter(tags=["settlement"])


@router.post("/upload_receipt", response_model=ReceiptOut)
def upload_receipt(
    claim_no: str = Form(), head: Head = Form(), file: UploadFile = File(),
    user: Employee = Depends(current_user), db: Session = Depends(get_db),
):
    """Upload one receipt (PNG or JPEG) and say what it is for. The AI reads it (OCR) and checks it fits, and the answer says
    whether it counts. Call it once per receipt."""
    data = file.file.read(settings.max_receipt_mb * 1024 * 1024 + 1)
    return Settlement(db).upload_receipt(user, claim_no, head, file.filename or "receipt", data)


@router.post("/submit_settlement", response_model=SubmitOut)
def submit_settlement(body: SubmitIn, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """Send the counted receipts to Finance. Returns the total, the advance, and what is payable or recoverable."""
    return Settlement(db).submit(user, body.claim_no)


@router.get("/get_receipt_image")
def get_receipt_image(line_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    """The photo of one uploaded bill (the line_id comes from get_claim). Only the claim's owner, its approvers (Finance included)
    and the admin may open it."""
    path, mime = Settlement(db).receipt_file(user, line_id)
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=300"})
