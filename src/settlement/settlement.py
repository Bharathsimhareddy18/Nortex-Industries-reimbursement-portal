"""The trip settlement: receipts in, AI checks, then off to Finance."""
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.setting import settings
from src.ai.groq import Groq
from src.claims.claims import Claims
from src.database.models import Approval, Category, Claim, Employee, Line
from src.errors import AppError
from src.flows.flows import Flows
from src.notifications.notifications import Notifications
from src.policy.policy import Policy
from src.pydantic_models.claim import ApproverOut
from src.pydantic_models.receipt import ClaimCheck, Head, ReceiptData, ReceiptOut, SubmitOut

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
IMAGE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}  # the first bytes of a real PNG / JPEG file


class Settlement:
    def __init__(self, db: Session, ai: Groq | None = None):
        self.db = db
        self.ai = ai or Groq()
        self.policy = Policy(db)
        self.notifications = Notifications(db)

    # ---------- receipts ----------

    def upload_receipt(self, user: Employee, claim_no: str, head: Head, filename: str, data: bytes) -> ReceiptOut:
        """Take one receipt image: read it (OCR), check it is not a repeat, check it fits what was claimed, save the result."""
        claim = self._get_claim(user, claim_no, "awaiting_settlement")
        if claim.flow is not None:
            Flows(self.db).check_head(claim, head)
        mime = self._image_type(data)
        receipt = self.ai.read_receipt(data, mime)
        path = self._save_file(claim_no, filename, data)
        key = self.policy.dedupe_key(receipt)

        earlier = self._earlier_line(key)
        if earlier is not None:
            issue = f"This bill was already uploaded (line {earlier.id} of claim {earlier.claim_no})."
            line = self._save_line(claim, head, receipt, path, key, "duplicate", issue, None)
            return self._result(line, receipt, None, False, issue, self.policy.receipt_message(line.status, line.reason))

        check = self._check(head, receipt)
        if check.matches:
            line = self._save_line(claim, head, receipt, path, key, "ok", None, check)
            return self._result(line, receipt, check, True, None, self.policy.receipt_message(line.status, line.reason))

        issue = check.issue or f"This looks like a {check.merchant_type} bill, not {head}."
        line = self._save_line(claim, head, receipt, path, key, "excluded", issue, check)
        self._report_mismatch(claim, receipt, issue)
        self.db.commit()
        return self._result(line, receipt, check, False, issue, self.policy.receipt_message(line.status, line.reason))

    def _check(self, head: str, receipt: ReceiptData) -> ClaimCheck:
        """Does the bill fit the claimed head? 'Other' is never questioned, so it skips the AI call."""
        if head not in settings.head_meanings:
            return ClaimCheck(merchant_type="not checked", matches=True)
        return self.ai.check_claim(head, receipt)

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

    def _save_line(self, claim: Claim, head: str, receipt: ReceiptData, path: str, key: str, status: str,
                   reason: str | None, check: ClaimCheck | None) -> Line:
        """One row of the Settlement Form. Only 'ok' rows are allowed any money."""
        line = Line(
            claim_no=claim.claim_no, section=self.policy.section_of(head), head=head, line_date=receipt.bill_date,
            description=(receipt.description or receipt.merchant)[:300], paid_by=receipt.paid_by, amount=receipt.amount,
            allowed=receipt.amount if status == "ok" else 0, reason=reason, proof_ref=receipt.bill_no, file_path=path,
            extracted={"receipt": receipt.model_dump(mode="json"), "check": check.model_dump(mode="json") if check else None},
            merchant_category=check.merchant_type[:30] if check else None, dedupe_key=key, status=status,
        )
        self.db.add(line)
        self.db.commit()
        return line

    def _report_mismatch(self, claim: Claim, receipt: ReceiptData, message: str) -> None:
        """Tell the claimant and everybody who approved this claim about a receipt that does not fit what was claimed."""
        approved = self.db.scalars(select(Approval.approver_code).where(Approval.claim_no == claim.claim_no, Approval.decision == "approved"))
        for code in {claim.employee_code, *approved}:
            self.notifications.send(code, claim.claim_no, f"Flagged receipt ({receipt.merchant}, INR {receipt.amount:,.2f}): {message}")

    def _result(self, line: Line, receipt: ReceiptData, check: ClaimCheck | None, matched: bool, issue: str | None, message: str) -> ReceiptOut:
        """The upload answer, including everything the model read."""
        return ReceiptOut(line_id=line.id, head=line.head, status=line.status, matched=matched, issue=issue, message=message,
                          extracted=receipt, check=check)

    # ---------- looking at a bill later ----------

    def receipt_file(self, user: Employee, line_id: int) -> tuple[Path, str]:
        """The saved image of one bill, for the people who may see the claim: its owner, anyone on its approval list (so Finance
        can check the invoice before verifying), and the admin. Returns the file and its type."""
        line = self.db.get(Line, line_id)
        if line is None:
            raise AppError(404, "Bill not found")
        if user.role != "Admin":
            Claims(self.db).visible_claim(user, line.claim_no)  # raises 403 / 404 when this person is not involved
        path = Path(line.file_path) if line.file_path else None
        # Only files inside our uploads folder are ever served, whatever the database says.
        if path is None or not path.is_file() or UPLOAD_DIR.resolve() not in path.resolve().parents:
            raise AppError(404, "The image of this bill is no longer available")
        return path, self._image_type(path.read_bytes()[:16])

    # ---------- submitting ----------

    def submit(self, user: Employee, claim_no: str) -> SubmitOut:
        """Send the settlement to Finance: needs at least one counted receipt. Creates the Finance steps from the template and tells the first."""
        claim = self._get_claim(user, claim_no, "awaiting_settlement")
        totals = self.policy.totals(claim_no, claim.advance_amount)
        if totals["paid_by_employee"] <= 0:
            raise AppError(422, "Upload at least one receipt that matches its claimed head before submitting")
        if claim.flow is not None:  # an admin-built flow decides what comes after the bills
            next_approver = Flows(self.db).finish_bills(claim)
            self.db.commit()
            return SubmitOut(claim_no=claim_no, status=claim.status, paid_by_employee=totals["paid_by_employee"], advance=totals["advance"],
                             payable=totals["payable"], recoverable=totals["recoverable"], next_approver=next_approver)
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
