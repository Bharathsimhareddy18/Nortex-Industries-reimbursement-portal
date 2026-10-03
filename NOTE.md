# Note: Nortex travel reimbursement

**Live:** https://nortex-reimbursement-production.up.railway.app/ (password `nortex123`; accounts are in the README)
**Run it:** `docker run --rm -p 8000:8000 -e GROQ_API_KEY=your-key bharathsimhareddy18/nortex-reimbursement:latest`, then open http://localhost:8000

## What it does

A trip goes from request to payout in one app. The employee raises a request with a reason and an optional advance. The amount sets the approval chain: Reporting Manager, then Head of Department, Head of Division and MD as it grows, and nobody approves their own claim. Finance releases the advance. After the trip the employee uploads photos of bills, an AI reads each one and checks it fits what was claimed, and Finance verifies and the Controller releases the payout. The employee always sees the status and who has it. An admin page shows everything, read-only.

## Decisions

- **FastAPI, Pydantic, SQLAlchemy, SQLite, plain HTML/JS, one Docker image.** Chosen to run end to end with one command and be easy to explain. The same app serves the API and the pages.
- **Two AI calls per bill, not one.** The first sees only the image and returns structured JSON. The second compares that JSON with the claimed expense type. The claim is hidden from the first call so it cannot bias the reading. A bill that does not fit is flagged, not counted, and the claimant and approvers are told.
- **Policy lives in `config/setting.py`**, not in code, so a threshold change is one edit. Approvers are built per level, then duplicates and the claimant are removed.
- **Money is exact decimals.** Payable is bills minus advance; if bills are lower, the difference is marked for payroll recovery.
- **Auth:** bcrypt-hashed passwords and a signed JWT on login. Every endpoint except login and `/health` is protected by default, and a test fails if one is left open.

## Handled from the pack

Advance capped at 60% of the estimate and reconciled at settlement; duplicate bills (same merchant, bill number, date, amount) caught; a bill that does not match its claimed head is excluded; the approval chain by amount (L1 to L4) with self-approval removed; hotel estimate from nights and the city-tier limit.

## Not done, honestly

- **The sample emails are not read.** Only uploaded PNG or JPEG bills are handled, so there is no email noise filtering.
- **Policy cuts are not applied.** Bills are paid in full: no hotel or meal cap, no laundry or mini-bar removal, no attendee check, no bills in another person's name.
- **No "send back with remarks"**, no second approval on the final amount, no 7-day deadline.
- **Duplicate check spans all employees.** A Finance person's own claim would stall.
- **Everyone shares one demo password**, and there is no rate limit or token revocation.
- **Data is not kept across a redeploy** (SQLite inside the container).
- Only a few automated tests (the login guard and the custom-flow path).
- Custom flows are a straight list: no conditions or branches yet, and the three built-in templates stay on the amount-based chain rather than being flows.

## Next

Per-user accounts, PostgreSQL, the policy cuts, email receipts, then the workflow gaps above. The full list is in the README.
