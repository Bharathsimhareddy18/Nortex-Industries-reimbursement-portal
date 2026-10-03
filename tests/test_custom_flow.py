"""An admin builds a flow, an employee raises a claim from it, and the claim walks every step to 'paid'. Runs on a throwaway database
and a fake AI, so it needs no key and leaves nortex.db alone."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import src.database.db as dbmod
from main import app
from src.ai.groq import Groq
from src.pydantic_models.receipt import ClaimCheck, ReceiptData

PNG = b"\x89PNG\r\n\x1a\n" + b"fake"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_FILE", tmp_path / "test.db")  # the app opens its database when it starts, so this is all it takes
    monkeypatch.setattr(Groq, "read_receipt", lambda self, image, mime: ReceiptData(
        merchant="Spice Terrace", bill_no="B-1", bill_date=date(2026, 6, 18), amount=Decimal("1500"), description="dinner"))
    monkeypatch.setattr(Groq, "check_claim", lambda self, head, receipt: ClaimCheck(merchant_type="restaurant", matches=True))
    with TestClient(app) as c:
        yield c


def login(client, email):
    r = client.post("/auth/login", json={"email": f"{email}@nortexindustries.com", "password": "nortex123"}).json()
    return {"emp-code": r["emp_code"], "session-token": r["session_token"]}


def form(id, title, *fields):
    return {"id": id, "type": "form", "title": title, "fields": list(fields)}


def field(name, label, type="text", **extra):
    return {"name": name, "label": label, "type": type, **extra}


FLOW = {
    "name": "Business client visit", "estimate_field": "budget",
    "steps": [
        form("s1", "Client details", field("client", "Client"), field("budget", "Budget", "money", min=1),
             field("advance_amount", "Advance", "money", required=False, min=0), field("why", "Why", "longtext", min=10)),
        {"id": "s2", "type": "approval", "approver": {"mode": "reporting_manager"}},
        {"id": "s3", "type": "approval", "approver": {"mode": "user", "emp_code": "NX-1108"}},
        form("s4", "Visit details", field("po_number", "PO number")),
        {"id": "s5", "type": "advance", "approver": {"mode": "user", "emp_code": "NX-3305"}, "amount_field": "advance_amount"},
        {"id": "s6", "type": "upload_bills", "heads": ["Meals", "Other"]},
        {"id": "s7", "type": "finance_review", "approver": {"mode": "user", "emp_code": "NX-3305"}},
        {"id": "s8", "type": "payout", "approver": {"mode": "user", "emp_code": "NX-3300"}},
    ],
}


def test_a_custom_flow_runs_from_request_to_payout(client):
    admin = login(client, "admin")
    made = client.post("/admin/templates", json=FLOW, headers=admin)
    assert made.status_code == 201, made.text
    template_id = made.json()["id"]
    assert [t["kind"] for t in client.get("/admin/templates", headers=admin).json()] == ["fixed", "fixed", "fixed", "flow"]

    employee, rm, hod, ravi, kavitha = (login(client, n) for n in ("chaitanya.reddy", "suresh.iyer", "meera.krishnan", "ravi.menon", "kavitha.balan"))
    fields = client.get(f"/get_template_required_fields?template_id={template_id}&template_name=Business client visit", headers=employee).json()
    assert [f["name"] for f in fields["fields"]] == ["client", "budget", "advance_amount", "why"] and len(fields["steps"]) == 8

    # advance above 60% of the budget is refused
    bad = {"client": "Vertex", "budget": "10000", "advance_amount": "7000", "why": "Quarterly review at the plant"}
    assert client.post("/create_claim", json={"template_id": template_id, "fields": bad}, headers=employee).status_code == 422

    ok = {**bad, "advance_amount": "5000"}
    claim = client.post("/create_claim", json={"template_id": template_id, "fields": ok}, headers=employee).json()
    no = claim["claim_no"]
    assert claim["status"] == "pending_approval"
    status = lambda: client.get(f"/get_claim?claim_no={no}", headers=employee).json()

    assert [p["claim_no"] for p in client.get("/get_pending_approvals", headers=rm).json()] == [no]
    assert client.get("/get_pending_approvals", headers=hod).json() == []  # not their turn yet
    assert client.post("/approve", json={"claim_no": no}, headers=hod).status_code == 403
    assert client.post("/approve", json={"claim_no": no}, headers=rm).status_code == 200
    assert client.post("/approve", json={"claim_no": no}, headers=hod).json()["status"] == "awaiting_input"

    # the employee has to answer the second form before anything else happens
    detail = status()
    assert detail["flow"]["form_title"] == "Visit details"
    assert client.post("/submit_step", json={"claim_no": no, "fields": {}}, headers=employee).status_code == 422
    assert client.post("/submit_step", json={"claim_no": no, "fields": {"po_number": "PO-7"}}, headers=employee).json()["status"] == "awaiting_advance"

    assert client.post("/approve", json={"claim_no": no}, headers=ravi).json()["status"] == "awaiting_settlement"
    assert status()["advance_amount"] == "5000.00" and status()["flow"]["heads"] == ["Meals", "Other"]

    def upload(head):
        return client.post("/upload_receipt", data={"claim_no": no, "head": head}, files={"file": ("b.png", PNG, "image/png")}, headers=employee)

    assert upload("Lodging").status_code == 422  # not an allowed head on this flow
    assert upload("Meals").json()["status"] == "ok"
    submitted = client.post("/submit_settlement", json={"claim_no": no}, headers=employee).json()
    assert submitted["status"] == "settlement_review" and submitted["next_approver"]["name"] == "Ravi Menon"
    assert submitted["recoverable"] == "3500.00"

    assert client.post("/approve", json={"claim_no": no}, headers=ravi).json()["next_approver"]["name"] == "Kavitha Balan"
    done = client.post("/approve", json={"claim_no": no}, headers=kavitha).json()
    assert done["status"] == "paid" and done["next_approver"] is None
    assert all(s["state"] == "done" for s in status()["flow"]["steps"])


def test_a_rejection_ends_the_claim(client):
    admin = login(client, "admin")
    template_id = client.post("/admin/templates", json=FLOW, headers=admin).json()["id"]
    employee, rm = login(client, "chaitanya.reddy"), login(client, "suresh.iyer")
    ok = {"client": "Vertex", "budget": "10000", "advance_amount": "0", "why": "Quarterly review at the plant"}
    no = client.post("/create_claim", json={"template_id": template_id, "fields": ok}, headers=employee).json()["claim_no"]
    assert client.post("/reject", json={"claim_no": no, "remarks": "No budget"}, headers=rm).json()["status"] == "rejected"
    assert client.post("/approve", json={"claim_no": no}, headers=rm).status_code == 409


def test_a_bad_flow_is_refused(client):
    admin = login(client, "admin")
    no_payout = {**FLOW, "steps": FLOW["steps"][:-1]}
    reply = client.post("/admin/templates", json=no_payout, headers=admin)
    assert reply.status_code == 422 and any("Payout" in p for p in reply.json()["problems"])
    assert client.post("/admin/templates", json=FLOW, headers=login(client, "chaitanya.reddy")).status_code == 403
    assert client.post("/admin/templates", json={**FLOW, "name": "Travelling"}, headers=admin).status_code == 409
