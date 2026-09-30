"""The trip settlement: receipts in, AI checks, then off to Finance."""
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.setting import settings
from src.ai.gemini import Gemini
from src.ai.jev import Jev
from src.database.models import Approval, Category, Claim, Employee, Line
from src.errors import AppError
from src.notifications.notifications import Notifications
from src.policy.policy import Policy
from src.pydantic_models.claim import ApproverOut
from src.pydantic_models.receipt import Head, ReceiptData, ReceiptOut, SubmitOut

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
IMAGE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}  # the first bytes of a real PNG / JPEG file


class Settlement:
    def __init__(self, db: Session, reader: Gemini | None = None, classifier: Jev | None = None):
        self.db = db
        self.reader = reader or Gemini()
        self.classifier = classifier or Jev()
        self.policy = Policy(db)
        self.notifications = Notifications(db)

    # ---------- receipts ----------

    def upload_receipt(self, user: Employee, claim_no: str, head: Head, filename: str, data: bytes) -> ReceiptOut:
        """Take one receipt image: read it (Gemini), check it is not a repeat, check it fits what was claimed (Jev), save the result."""
        claim = self._get_claim(user, claim_no, "awaiting_settlement")
        mime = self._image_type(data)
        receipt = self.reader.read_receipt(data, mime)
        path = self._save_file(claim_no, filename, data)
        key = self.policy.dedupe_key(receipt)

        earlier = self._earlier_line(key)
        if earlier is not None:
            message = f"This bill was already uploaded (line {earlier.id} of claim {earlier.claim_no}), so it is not counted again."
            line = self._save_line(claim, head, receipt, path, key, "duplicate", message, None, 0.0)
            return self._result(line, receipt, None, False, message)

        merchant_type, confidence = self.classifier.classify(self._describe(receipt))
        if self.policy.head_matches(head, merchant_type):
            line = self._save_line(claim, head, receipt, path, key, "ok", None, merchant_type, confidence)
            return self._result(line, receipt, merchant_type, True, "Matches what you claimed. It will be counted.")

        message = f"This looks like a {merchant_type} bill, but you claimed it as {head}. It is flagged and not counted."
        line = self._save_line(claim, head, receipt, path, key, "excluded", message, merchant_type, confidence)
        self._report_mismatch(claim, line, receipt, message)
        self.db.commit()
        return self._result(line, receipt, merchant_type, False, message)

    def _get_claim(self, user: Employee, claim_no: str, status: str) -> Claim:
        """The claim, if it exists, belongs to the user and is in the right stage."""
        claim = self.db.get(Claim, claim_no)
        if claim is None:
            raise AppError(404, "Claim not found")
        if claim.employee_code != user.emp_code:
            raise AppError(403, "This is not your claim")
        if claim.status != status:
            raise AppError(409, f"This claim is '{claim.status}'; this step needs it to be '{status}'")
        return claim

    def _image_type(self, data: bytes) -> str:
        """PNG or JPEG only, judged by the file's own first bytes (not the name or what the browser says), and not too big."""
        if len(data) > settings.max_receipt_mb * 1024 * 1024:
            raise AppError(413, f"The image is larger than {settings.max_receipt_mb} MB")
        for signature, mime in IMAGE_SIGNATURES.items():
            if data.startswith(signature):
                return mime
        raise AppError(415, "Only PNG and JPEG images are accepted")

    def _save_file(self, claim_no: str, filename: str, data: bytes) -> str:
        """Keep the image on disk under the claim's folder, with a random prefix so two files with one name never overwrite each other."""
        folder = UPLOAD_DIR / claim_no
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{secrets.token_hex(4)}_{Path(filename).name}"
        path.write_bytes(data)
        return str(path)

    def _earlier_line(self, key: str) -> Line | None:
        """A counted receipt with the same merchant, bill number, date and amount, on any claim."""
        return self.db.scalars(select(Line).where(Line.dedupe_key == key, Line.status == "ok")).first()

    def _describe(self, receipt: ReceiptData) -> str:
        """The text Jev reads: what Gemini found on the bill."""
        return f"{receipt.merchant}. {receipt.description}. Items: {', '.join(receipt.items)}"

    def _save_line(self, claim: Claim, head: str, receipt: ReceiptData, path: str, key: str, status: str,
                   reason: str | None, merchant_type: str | None, confidence: float) -> Line:
        """One row of the Settlement Form. Only 'ok' rows are allowed any money."""
        line = Line(
            claim_no=claim.claim_no, section=self.policy.section_of(head), head=head, line_date=receipt.bill_date,
            description=(receipt.description or receipt.merchant)[:300], paid_by=receipt.paid_by, amount=receipt.amount,
            allowed=receipt.amount if status == "ok" else 0, reason=reason, proof_ref=receipt.bill_no, file_path=path,
            extracted={"receipt": receipt.model_dump(mode="json"), "jev_confidence": confidence},
            merchant_category=merchant_type, dedupe_key=key, status=status,
        )
        self.db.add(line)
        self.db.commit()
        return line

    def _report_mismatch(self, claim: Claim, line: Line, receipt: ReceiptData, message: str) -> None:
        """Tell the claimant and everybody who approved this claim about a receipt that does not fit what was claimed."""
        approved = self.db.scalars(select(Approval.approver_code).where(Approval.claim_no == claim.claim_no, Approval.decision == "approved"))
        for code in {claim.employee_code, *approved}:
            self.notifications.send(code, claim.claim_no, f"Flagged receipt ({receipt.merchant}, INR {receipt.amount:,.2f}): {message}")

    def _result(self, line: Line, receipt: ReceiptData, merchant_type: str | None, matched: bool, message: str) -> ReceiptOut:
        """The upload answer."""
        return ReceiptOut(
            line_id=line.id, head=line.head, merchant=receipt.merchant, bill_no=receipt.bill_no, bill_date=receipt.bill_date,
            amount=receipt.amount, merchant_type=merchant_type, matched=matched, status=line.status, message=message,
        )

    # ---------- submitting ----------

    def submit(self, user: Employee, claim_no: str) -> SubmitOut:
        """Send the settlement to Finance: needs at least one counted receipt. Creates the Finance steps from the template and tells the first."""
        claim = self._get_claim(user, claim_no, "awaiting_settlement")
        totals = self.policy.totals(claim_no, claim.advance_amount)
        if totals["paid_by_employee"] <= 0:
            raise AppError(422, "Upload at least one receipt that matches its claimed head before submitting")
        steps = self._finance_steps(claim)
        for number, step in enumerate(steps, start=1):
            self.db.add(Approval(claim_no=claim_no, phase="settlement", step=number, role="Finance", action=step["action"], approver_code=step["emp_code"]))
        claim.status = "settlement_review"
        first = self.db.get(Employee, steps[0]["emp_code"])
        self.notifications.send(first.emp_code, claim_no,
                                f"{user.name} ({user.emp_code}) submitted a settlement of INR {totals['paid_by_employee']:,.2f} "
                                f"(advance INR {claim.advance_amount:,.2f}). Please verify it.")
        self.db.commit()
        return SubmitOut(
            claim_no=claim_no, status=claim.status, paid_by_employee=totals["paid_by_employee"], advance=totals["advance"],
            payable=totals["payable"], recoverable=totals["recoverable"],
            next_approver=ApproverOut(emp_code=first.emp_code, name=first.name, role="Finance"),
        )

    def _finance_steps(self, claim: Claim) -> list[dict]:
        """The settlement-stage Finance steps of the claim's template (Ravi verifies, Kavitha releases the payout)."""
        template = self.db.get(Category, claim.category_id)
        steps = [s for s in template.config.get("finance_steps", []) if s["phase"] == "settlement"]
        if not steps:
            raise AppError(500, "This template has no Finance steps for the settlement")
        return steps
