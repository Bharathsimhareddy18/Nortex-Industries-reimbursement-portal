"""Admin-built flows: a template is an ordered list of steps (ask for fields, approve, release an advance, upload bills,
finance review, payout), stored as JSON. A claim copies the list when it is raised and walks through it one step at a time.

The three fixed templates do not use this: they keep the amount-based L1 to L4 chain in approvals.py / claims.py.
"""
import copy
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.db import utc_now
from src.database.models import Approval, Category, Claim, Employee
from src.errors import AppError
from src.notifications.notifications import Notifications
from src.policy.policy import Policy
from src.pydantic_models.approval import ApproveOut, RejectOut
from src.pydantic_models.claim import ApproverOut, FlowStepView, FlowViewOut
from src.pydantic_models.flow import AdminTemplateOut, FlowIn
from src.pydantic_models.template import FieldOut
from src.templates.templates import Templates

# What each step that needs a person does: (the approvals.action it creates, the claim status while it waits, its label).
PERSON_STEPS = {
    "approval": ("approve", "pending_approval", "Approval"),
    "advance": ("release_advance", "awaiting_advance", "Advance"),
    "finance_review": ("verify", "settlement_review", "Finance review"),
    "payout": ("release_payment", "settlement_review", "Payout"),
}
STEP_TITLES = {**{kind: label for kind, (_, _, label) in PERSON_STEPS.items()}, "upload_bills": "Upload bills"}


def advance_requested(claim: Claim) -> Decimal:
    """The advance a flow claim asked for: the answer in the money field the advance step points at (0 if there is no such step)."""
    for step in (claim.flow or {}).get("steps", []):
        if step["type"] == "advance":
            return Decimal(str(claim.details.get(step["amount_field"], 0)))
    return Decimal("0")


class Flows:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = Notifications(db)
        self.policy = Policy(db)
        self.templates = Templates(db)

    # ---------- templates (admin) ----------

    def list_templates(self) -> list[AdminTemplateOut]:
        return [self.template_out(t) for t in self.templates.list_all()]

    def template_out(self, template: Category) -> AdminTemplateOut:
        if "flow" in template.config:
            return AdminTemplateOut(id=template.id, name=template.name, kind="flow", flow=template.config["flow"])
        return AdminTemplateOut(id=template.id, name=template.name, kind="fixed", fields=[FieldOut(**f) for f in template.config["fields"]])

    def save_template(self, data: FlowIn, template_id: int | None = None) -> AdminTemplateOut:
        """Create a flow template, or replace the flow of an existing one. Claims already raised keep the flow they started with."""
        self._check(data)
        flow = {"estimate_field": data.estimate_field, "steps": data.model_dump(mode="json", exclude_none=True)["steps"]}
        clash = self.db.scalar(select(Category).where(Category.name == data.name.strip()))
        if template_id is None:
            if clash is not None:
                raise AppError(409, "A template with this name already exists")
            template = Category(name=data.name.strip(), config={"flow": flow})
            self.db.add(template)
        else:
            template = self.templates.get(template_id)
            if "flow" not in template.config:
                raise AppError(409, "The three built-in templates cannot be changed here")
            if clash is not None and clash.id != template.id:
                raise AppError(409, "A template with this name already exists")
            template.name, template.config = data.name.strip(), {"flow": flow}
        self.db.commit()
        return self.template_out(template)

    def _check(self, data: FlowIn) -> None:
        """The rules a flow must follow so a claim can always finish. Raised as one 422 listing every problem."""
        steps = [s.model_dump(exclude_none=True) for s in data.steps]
        problems = []
        kinds = [s["type"] for s in steps]
        if kinds[0] != "form":
            problems.append("The flow must start with a form (the employee's request).")
        if kinds[-1] != "payout" or kinds.count("payout") != 1:
            problems.append("The flow must end with exactly one Payout step.")
        for kind, label in (("upload_bills", "Upload bills"), ("advance", "Advance")):
            if kinds.count(kind) > 1:
                problems.append(f"Use '{label}' only once.")
        if len({s["id"] for s in steps}) != len(steps):
            problems.append("Two steps share the same id.")

        fields = [f for s in steps if s["type"] == "form" for f in s["fields"]]
        names = [f["name"] for f in fields]
        if len(set(names)) != len(names):
            problems.append("Two fields share the same name; give each field a different label.")
        money = {f["name"] for f in fields if f["type"] == "money"}
        if data.estimate_field and data.estimate_field not in money:
            problems.append("The estimate must be one of the money fields.")
        for s in steps:
            if s["type"] == "advance" and s["amount_field"] not in money:
                problems.append("The advance must point at a money field.")
            if s["type"] in ("advance", "finance_review", "payout") and s["approver"]["mode"] != "user":
                problems.append(f"'{STEP_TITLES[s['type']]}' must be given to a named person.")
            code = s.get("approver", {}).get("emp_code")
            if code and self.db.get(Employee, code) is None:
                problems.append(f"No employee with code {code}.")
        if problems:
            raise AppError(422, "This flow cannot be saved yet", problems)

    # ---------- raising a claim and filling later forms ----------

    def create_claim(self, employee: Employee, template: Category, fields: dict, claim_no: str) -> tuple[Claim, list[tuple[str, Employee]]]:
        """Raise a claim from a flow template: the first form is the request; then the claim moves on through the flow."""
        flow = copy.deepcopy(template.config["flow"])  # frozen for this claim
        claim = Claim(claim_no=claim_no, employee_code=employee.emp_code, category_id=template.id, status="awaiting_input", level=0,
                      details={}, estimated_amount=Decimal("0"), flow=flow, current_step=0)
        self._answer(claim, flow["steps"][0], fields)
        self.db.add(claim)
        self.db.flush()
        self._enter(claim, 1)
        self.db.commit()
        return claim, self._people_preview(claim, employee)

    def submit_step(self, user: Employee, claim_no: str, fields: dict) -> Claim:
        """The employee fills a form step that comes after the request (a later 'ask for fields' block)."""
        claim = self.db.get(Claim, claim_no)
        if claim is None:
            raise AppError(404, "Claim not found")
        if claim.employee_code != user.emp_code:
            raise AppError(403, "This is not your claim")
        if claim.flow is None or claim.status != "awaiting_input":
            raise AppError(409, f"This claim is '{claim.status}'; there is no form waiting for you")
        self._answer(claim, claim.flow["steps"][claim.current_step], fields)
        self._enter(claim, claim.current_step + 1)
        self.db.commit()
        return claim

    def _answer(self, claim: Claim, step: dict, fields: dict) -> None:
        """Check one form's answers, keep them on the claim, and re-check the advance cap once both amounts are known."""
        clean = self.templates.clean_step(step["fields"], fields, "flow")
        claim.details = {**claim.details, **clean}
        estimate_field = claim.flow.get("estimate_field")
        if estimate_field and clean.get(estimate_field) is not None:
            claim.estimated_amount = Decimal(str(clean[estimate_field]))
        advance = advance_requested(claim)
        if advance > 0 and claim.estimated_amount > 0:
            self.policy.check_advance(claim.estimated_amount, advance)

    def check_head(self, claim: Claim, head: str) -> None:
        """A bill may only be for one of the heads the admin allowed on the Upload bills step."""
        allowed = claim.flow["steps"][claim.current_step].get("heads", [])
        if head not in allowed:
            raise AppError(422, f"This claim accepts bills for: {', '.join(allowed)}")

    def finish_bills(self, claim: Claim) -> ApproverOut | None:
        """The employee submitted the bills: go on to the next step. Returns who it went to, if a person."""
        self._enter(claim, claim.current_step + 1)
        pending = self._pending(claim)
        return self._as_approver(pending) if pending else None

    # ---------- walking the flow ----------

    def _enter(self, claim: Claim, index: int) -> None:
        """Start the step at `index` and stop where the claim has to wait for someone. Steps whose person is the claimant, or nobody, are skipped."""
        steps = claim.flow["steps"]
        employee = self.db.get(Employee, claim.employee_code)
        while index < len(steps):
            step = steps[index]
            kind = step["type"]
            claim.current_step = index
            if kind == "form":
                claim.status = "awaiting_input"
                self.notifications.send(employee.emp_code, claim.claim_no, f"Please fill in the next form: {step['title']}.")
                return
            if kind == "upload_bills":
                claim.status = "awaiting_settlement"
                self.notifications.send(employee.emp_code, claim.claim_no, "Please upload your bills and receipts to settle this claim.")
                return
            action, status, _ = PERSON_STEPS[kind]
            person = self._resolve(step["approver"], employee)
            if person is not None:
                role = "Reporting Manager" if step["approver"]["mode"] == "reporting_manager" else person.role
                self.db.add(Approval(claim_no=claim.claim_no, phase="flow", step=index, role=role, action=action, approver_code=person.emp_code))
                claim.status = status
                self.notifications.send(person.emp_code, claim.claim_no, self._ask(claim, employee, action))
                return
            index += 1
        self._finish(claim, employee, len(steps))

    def _finish(self, claim: Claim, employee: Employee, step_count: int) -> None:
        """Past the last step: the claim is paid, and the employee is told what happens to the money."""
        claim.current_step = step_count
        claim.status = "paid"
        claim.payment_date = self.policy.next_payment_date(utc_now().date())
        totals = self.policy.totals(claim.claim_no, claim.advance_amount)
        if totals["payable"] > 0:
            message = f"INR {totals['payable']:,.2f} has been dispatched to you. It will be paid in the payment run on {claim.payment_date:%d %b %Y}."
        elif totals["recoverable"] > 0:
            message = (f"Your claim is INR {totals['recoverable']:,.2f} below the advance you took, so that amount will be deducted "
                       "from your next payroll. Nothing is payable to you.")
        else:
            message = "Your claim is complete. Nothing more is due."
        self.notifications.send(employee.emp_code, claim.claim_no, message)

    def _ask(self, claim: Claim, employee: Employee, action: str) -> str:
        """The message to the person whose turn it is."""
        who = f"{employee.name} ({employee.emp_code})"
        if action == "release_advance":
            return f"All approvals are done. Please release the advance of INR {advance_requested(claim):,.2f} to {who}."
        if action == "verify":
            return f"{who}'s settlement is ready. Please verify it."
        if action == "release_payment":
            totals = self.policy.totals(claim.claim_no, claim.advance_amount)
            return f"{who}'s settlement is verified. Payable INR {totals['payable']:,.2f}, recoverable INR {totals['recoverable']:,.2f}. Please release it."
        amount = f" for INR {claim.estimated_amount:,.2f}" if claim.estimated_amount > 0 else ""
        return f"{who} requests your approval{amount} ({self.db.get(Category, claim.category_id).name})."

    def _resolve(self, approver: dict, claimant: Employee) -> Employee | None:
        """The person an approver setting points at, or None if nobody (or only the claimant): nobody acts on their own claim."""
        if approver["mode"] == "user":
            person = self.db.get(Employee, approver["emp_code"])
        else:
            code = self.policy.get_reporting_manager_code(claimant.emp_code)
            person = self.db.get(Employee, code) if code else None
        return None if person is None or person.emp_code == claimant.emp_code else person

    def _pending(self, claim: Claim) -> Approval | None:
        return self.db.scalars(select(Approval).where(Approval.claim_no == claim.claim_no, Approval.decision == "pending")
                               .order_by(Approval.step)).first()

    def _as_approver(self, step: Approval) -> ApproverOut:
        person = self.db.get(Employee, step.approver_code)
        return ApproverOut(emp_code=person.emp_code, name=person.name, role=step.role)

    # ---------- the two decisions ----------

    def _my_step(self, user: Employee, claim: Claim) -> Approval:
        if claim.employee_code == user.emp_code:
            raise AppError(403, "You cannot act on your own claim")
        pending = self._pending(claim)
        if pending is None:
            raise AppError(409, f"This claim is '{claim.status}', there is nothing to decide")
        if pending.approver_code != user.emp_code:
            raise AppError(403, "No approval is waiting on you for this claim")
        return pending

    def approve(self, user: Employee, claim: Claim) -> ApproveOut:
        step = self._my_step(user, claim)
        step.decision, step.decided_at = "approved", utc_now()
        if step.action == "release_advance":
            claim.advance_amount = advance_requested(claim)
            self.notifications.send(claim.employee_code, claim.claim_no, f"The advance of INR {claim.advance_amount:,.2f} has been released.")
        elif step.action != "release_payment":
            self.notifications.send(claim.employee_code, claim.claim_no, f"{user.name} ({step.role}) approved your claim.")
        self._enter(claim, claim.current_step + 1)
        self.db.commit()
        following = self._pending(claim)
        return ApproveOut(claim_no=claim.claim_no, status=claim.status, next_approver=self._as_approver(following) if following else None)

    def reject(self, user: Employee, claim: Claim, remarks: str) -> RejectOut:
        step = self._my_step(user, claim)
        step.decision, step.remarks, step.decided_at = "rejected", remarks, utc_now()
        claim.status = "rejected"
        self.notifications.send(claim.employee_code, claim.claim_no, f"{user.name} ({step.role}) rejected your claim: {remarks}")
        self.db.commit()
        return RejectOut(claim_no=claim.claim_no, status=claim.status)

    # ---------- what the screens show ----------

    def reason_text(self, claim: Claim) -> str | None:
        """What approvers read as 'why': the first paragraph-type answer on the claim, if the flow asked for one."""
        for step in claim.flow["steps"]:
            for field in step.get("fields", []) if step["type"] == "form" else []:
                if field["type"] == "longtext" and claim.details.get(field["name"]):
                    return claim.details[field["name"]]
        return None

    def preview(self, steps: list[dict]) -> list[dict]:
        """A flow as a plain list for the request page: what will happen after the employee submits."""
        return [{"type": s["type"], "title": s["title"] if s["type"] == "form" else STEP_TITLES[s["type"]]} for s in steps]

    def _people_preview(self, claim: Claim, employee: Employee) -> list[tuple[str, Employee]]:
        """Everyone who will be asked to act, in order, for the 'approvers' list shown after raising a request."""
        people = []
        for step in claim.flow["steps"]:
            if step["type"] in PERSON_STEPS:
                person = self._resolve(step["approver"], employee)
                if person is not None:
                    people.append((STEP_TITLES[step["type"]], person))
        return people

    def view(self, claim: Claim) -> FlowViewOut:
        """The claim's flow with each step marked done, current or pending, for the tracker and the form or bill upload that is due."""
        employee = self.db.get(Employee, claim.employee_code)
        steps = claim.flow["steps"]
        done_to = len(steps) if claim.status == "paid" else claim.current_step
        views = []
        for i, step in enumerate(steps):
            who = None
            if step["type"] in PERSON_STEPS:
                person = self._resolve(step["approver"], employee)
                who = person.name if person else None
            views.append(FlowStepView(
                id=step["id"], type=step["type"], title=step["title"] if step["type"] == "form" else STEP_TITLES[step["type"]], who=who,
                state="done" if i < done_to else "current" if i == done_to else "pending"))
        view = FlowViewOut(steps=views)
        if claim.current_step < len(steps) and claim.status not in ("paid", "rejected"):
            now = steps[claim.current_step]
            if now["type"] == "form":
                view.form_title, view.form_fields = now["title"], [FieldOut(**f) for f in now["fields"]]
            elif now["type"] == "upload_bills":
                view.heads = now["heads"]
        return view
