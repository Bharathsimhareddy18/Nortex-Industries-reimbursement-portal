# Nortex Reimbursement API

Reference for building the UI. Every example below is a real response from the running API.

- Run locally: `uvicorn main:app --reload` (default `http://127.0.0.1:8000`).
- Live, clickable docs generated from the code: `/docs`. Raw schema: `/openapi.json`.
- The web pages are served by this same app, so they need no CORS. Pages from any other website are refused by the browser.
- Every endpoint except `POST /auth/login` and `GET /health` requires the login headers (see Conventions); this is enforced for the whole app, not endpoint by endpoint.

## 1. Conventions

### Logging in
`POST /auth/login` returns `emp_code` and `session_token`. **Send both as headers on every other call:**

```
emp-code: NX-4471
session-token: XJVwKO4MT5wu_iFyvaVXwl5PvXlKH4BOeyFY1t1wIsQ
```

The token must belong to that `emp-code`, otherwise it is a 401. The token is a JWT and lasts 12 hours. On any **401, send the user back to the login page**.
The caller's identity always comes from these headers, never from a request body.

### Demo users
Password for everyone: `nortex123`.

| Email | Name | Role | Reports to |
|---|---|---|---|
| chaitanya.reddy@nortexindustries.com | Chaitanya Reddy | Employee | Suresh |
| deepa.nair@nortexindustries.com | Deepa Nair | Employee | Suresh |
| imran.qureshi@nortexindustries.com | Imran Qureshi | Employee | Suresh |
| suresh.iyer@nortexindustries.com | Suresh Iyer | Reporting Manager | Meera |
| meera.krishnan@nortexindustries.com | Meera Krishnan | Head of Department (Sales) | Arvind |
| arvind.rao@nortexindustries.com | Arvind Rao | Head of Division | Nandita |
| nandita.shah@nortexindustries.com | Nandita Shah | MD | none |
| ravi.menon@nortexindustries.com | Ravi Menon | Finance (releases advances, verifies claims) | Kavitha |
| kavitha.balan@nortexindustries.com | Kavitha Balan | Finance, Controller (releases the payout) | Arvind |
| admin@nortexindustries.com | Portal Admin | Admin (read-only view of everything; code `NX-0001`) | none |

### Errors
Every error is JSON:

```json
{ "detail": "An earlier approver has not approved yet", "problems": [] }
```

`detail` is a message to show the user. `problems` is a list of messages (field errors, things to fix); it can be missing on a 401.

| Status | Meaning |
|---|---|
| 401 | missing, wrong or expired session: go to login |
| 403 | you are not allowed (not your claim, not your turn to approve) |
| 404 | claim / template not found |
| 409 | the claim is in the wrong state for this action |
| 413 / 415 | receipt too large (over 5 MB) / not a PNG or JPEG |
| 422 | invalid input; `problems` lists each field |
| 502 / 503 | the AI service failed / is not configured |

### Formats
Money comes back as **strings** (`"48000.00"`). Send money as a string or a number. Dates are `YYYY-MM-DD`, date-times ISO 8601 (`2026-06-16T07:55:00`). Times in responses are UTC.

### The life of a claim (`status`)

```
pending_approval --(managers approve in order)--> awaiting_advance --(Ravi releases)--> awaiting_settlement
                 \-(no advance asked)--------------------------------------------------^
awaiting_settlement --(employee submits receipts)--> settlement_review --(Ravi verifies, Kavitha pays)--> paid
any open stage --(someone rejects)--> rejected
```

| Status | Who has to act | What to show |
|---|---|---|
| `pending_approval` | the next approver | "Waiting for <name>" |
| `awaiting_advance` | Ravi | "Waiting for Finance to release your advance" |
| `awaiting_settlement` | the employee | upload receipts, then submit |
| `settlement_review` | Ravi, then Kavitha | "With Finance" |
| `paid` | nobody | done |
| `rejected` | nobody | done; the reason is in the notifications |

### Approval levels (who approves a request)
Decided by the estimated amount; any international trip is L4. The claimant is never their own approver.

| Level | Amount | Approvers, in order |
|---|---|---|
| L1 | up to 25,000 | Reporting Manager |
| L2 | 25,001 to 75,000 | + Head of Department |
| L3 | 75,001 to 2,00,000 | + Head of Division |
| L4 | above 2,00,000 or international | + MD |

If an advance is requested, Finance (Ravi) is added last to release it. Approvals are **one after another**: each approver is told only when the one before has approved.

---

## 2. Endpoints

All endpoints except `/auth/login` and `/` need the two headers. "Screen" says where the UI would use it.

### `POST /auth/login`
Log in. **Screen: login page.**

Body:
```json
{ "email": "chaitanya.reddy@nortexindustries.com", "password": "nortex123" }
```
Response `200`:
```json
{ "emp_code": "NX-4471", "session_token": "XJVwKO4MT5wu_iFyvaVXwl5PvXlKH4BOeyFY1t1wIsQ" }
```
Errors: `401` wrong email or password (same message for both, on purpose). Email ignores case and spaces.
Keep both values (for example in `localStorage`) and send them as headers from now on.

### `GET /auth/me`
The full profile of the logged-in person. **Screen: anywhere you need the name or the reporting manager.**

Response `200`:
```json
{ "emp_code": "NX-4471", "name": "Chaitanya Reddy", "email": "chaitanya.reddy@nortexindustries.com",
  "designation": "Manager - Key Accounts", "department": "Sales", "cost_centre": "CE110", "city": "Pune",
  "reporting_manager_code": "NX-2210", "role": "Employee" }
```
`role` is one of `Employee`, `Reporting Manager`, `Head of Department`, `Head of Division`, `MD`, `Finance`, `Admin`.

### `GET /dashboard/me`
The short profile for the dashboard header. **Screen: dashboard.** `role` tells you which menus to show (for example Approvals for managers and Finance).

Response `200`:
```json
{ "emp_code": "NX-4471", "email": "chaitanya.reddy@nortexindustries.com", "designation": "Manager - Key Accounts",
  "department": "Sales", "role": "Employee" }
```

### `GET /get_templates`
The list of things an employee can claim. **Screen: "New request" picker.**

Response `200`:
```json
[ { "template_id": 1, "template_name": "Travelling" },
  { "template_id": 2, "template_name": "Food" },
  { "template_id": 3, "template_name": "Hotel stay" } ]
```

### Custom flows
Templates built by an admin appear in `GET /get_templates` like the built-in ones. For a flow template, `get_template_required_fields` returns the fields of its first form and an extra `steps` list (`[{type, title}]`) for showing what happens next. `create_claim` works as usual (`level` is 0 and `estimated_amount` is 0 unless the flow names an estimate field; `approvers` lists everyone who will act, in order). A new status `awaiting_input` means the claim waits for the employee to fill a later form: `get_claim` then returns a `flow` object (`steps` with `state` done/current/pending, plus `form_title` and `form_fields` for the form due, or `heads` while bills are due), and the employee sends the answers to:

`POST /submit_step` with `{ "claim_no": "TRQ-2026-0003", "fields": { "po_number": "PO-7781" } }` returns `{ "claim_no", "status" }`.

Admin only: `GET /admin/templates` (all templates; flows include their steps), `POST /admin/templates` and `PUT /admin/templates/{id}` with `{ "name", "estimate_field", "steps": [...] }`. A flow that breaks a rule is a `422` whose `problems` lists each one. See data_model.md for the step shapes.

### `GET /get_template_required_fields?template_id=1&template_name=Travelling`
The fields of one template, so the form can be drawn from data. **Screen: the request form.** The id and the name must both match, otherwise `404`.

Response `200` (shortened):
```json
{ "template_id": 1, "template_name": "Travelling",
  "fields": [
    { "name": "destination", "label": "Destination", "type": "text", "required": true, "choices": null, "min": null, "default": null },
    { "name": "mode_of_transport", "label": "Mode of transport", "type": "choice", "required": true, "choices": ["Air", "Train", "Bus", "Car"], "min": null, "default": null },
    { "name": "number_of_days", "label": "Number of days", "type": "integer", "required": true, "choices": null, "min": 1.0, "default": null },
    { "name": "departure_time", "label": "Departure time", "type": "datetime", "required": true, "choices": null, "min": null, "default": null },
    { "name": "estimated_trip_cost", "label": "Estimated trip cost", "type": "money", "required": true, "choices": null, "min": 0.01, "default": null },
    { "name": "advance_requested", "label": "Advance requested", "type": "money", "required": false, "choices": null, "min": 0.0, "default": 0 },
    { "name": "is_international", "label": "International trip", "type": "boolean", "required": false, "choices": null, "min": null, "default": false }
  ] }
```

How to draw each `type`:

| `type` | Input |
|---|---|
| `text` | text box |
| `integer` | number box, whole numbers, at least `min` |
| `money` | number box with 2 decimals, at least `min` |
| `datetime` | date and time picker, send ISO 8601 |
| `boolean` | checkbox |
| `choice` | dropdown of `choices` (send the value as it is: a string, or the number 1, 2, 3 for `city_tier`) |
| `longtext` | a multi-line text box (a paragraph), at least `min` characters, at most 1000 |

Fields the three templates ask for:

| Template | Fields |
|---|---|
| 1 Travelling | `destination`, `mode_of_transport`, `number_of_days`, `departure_time`, `estimated_trip_cost`, optional `advance_requested`, optional `is_international`, **`reason`** |
| 2 Food | `amount`, `city`, `city_tier` (1, 2 or 3), **`reason`** |
| 3 Hotel stay | `hotel_name`, `city`, `city_tier` (1, 2 or 3), `number_of_days`, **`reason`** |

**`reason`** (type `longtext`, required, at least 10 characters) is on every template: *what is this for, and why is the money needed?* It is stored with the claim and shown to every approver: it comes back as `reason` in `get_pending_approvals` and inside `fields` in `get_claim`.

The amount that decides the approval level is `estimated_trip_cost` (Travelling), `amount` (Food), and for Hotel stay it is nights multiplied by the lodging limit of the tier (Tier 1: 6,000 a night).

### `POST /create_claim`
Raise a request from a template. The claimant is the logged-in user. **Screen: request form submit.**

Body:
```json
{ "template_id": 1,
  "fields": { "destination": "Bengaluru", "mode_of_transport": "Air", "number_of_days": 5,
              "departure_time": "2026-06-16T07:55:00", "estimated_trip_cost": "48000", "advance_requested": "20000",
              "reason": "Customer review at Vertex Technologies and the plant visit, to close the Q3 pricing agreement." } }
```
Response `201`:
```json
{ "claim_no": "TRQ-2026-0001", "status": "pending_approval", "level": 2, "estimated_amount": "48000.00",
  "approvers": [ { "emp_code": "NX-2210", "name": "Suresh Iyer", "role": "Reporting Manager" },
                 { "emp_code": "NX-1108", "name": "Meera Krishnan", "role": "Head of Department" } ] }
```
`claim_no` is the claim's id in every other call. `approvers` is the order they will approve in. If nobody has to approve (for example the MD claiming), `approvers` is empty and `status` is already `awaiting_settlement`.

Errors: `422` with `problems`, for a missing or unknown field, a bad value, or an advance above 60% of the estimate:
```json
{ "detail": "Some fields are missing or invalid", "problems": ["city: Field required", "city_tier: Input should be 1, 2 or 3"] }
```

### `GET /get_pending_approvals`
The logged-in user's approval queue: the claims where **it is their turn to act right now**, oldest first. **Screen: the Approvals page for managers and Finance.** Use this, not the notifications, to decide which claims get Approve / Reject buttons. When someone approves or rejects, the claim leaves the list on the next call, so the UI needs no saved memory of what was decided. An employee, or anyone with nothing waiting, gets `[]`.

Response `200`:
```json
[ { "claim_no": "TRQ-2026-0001", "claimant_code": "NX-4471", "claimant_name": "Chaitanya Reddy",
    "template_name": "Travelling", "level": 2, "status": "pending_approval",
    "estimated_amount": "48000.00", "advance_requested": "20000",
    "reason": "Customer review at Vertex Technologies and the plant visit, to close the Q3 pricing agreement.", "phase": "request",
    "role": "Reporting Manager", "action": "approve", "created_at": "2026-10-01T02:44:04" } ]
```
`action` says what the user is being asked to do, so the button can be labelled to match:

| `action` | Who | Button |
|---|---|---|
| `approve` | a manager | Approve / Reject |
| `release_advance` | Ravi | Release advance (`advance_requested` is the amount) |
| `verify` | Ravi | Verify the settlement |
| `release_payment` | Kavitha | Release payout |

A claim is listed only when all earlier approvers have approved, it is in a stage that is still running, and it is not the user's own claim. Anything listed here can be sent to `/approve` or `/reject`.

### `GET /get_all_notifications`
The logged-in user's inbox, newest first. **Screen: notification bell and list.** It is a message list only: to know which claims can be approved, use `get_pending_approvals`.

Response `200`:
```json
[ { "id": 1, "claim_no": "TRQ-2026-0001",
    "message": "Chaitanya Reddy (NX-4471) requests approval for INR 48,000.00 (Travelling, level L2).",
    "is_read": false, "created_at": "2026-09-30T19:57:32" } ]
```
What people receive:

| Who | When |
|---|---|
| the next approver | it is their turn to approve |
| Ravi | all managers approved, please release the advance |
| the claimant | each approval, "fully approved", advance released, a receipt was flagged, rejected, final payment |
| Ravi, then Kavitha | settlement submitted, then verified |
| the claimant and everyone who approved | a receipt did not match what was claimed |

There is no "mark as read" endpoint yet, so `is_read` is always `false`.

### `POST /approve`
Approve a claim as the logged-in user. **Screen: approve button for managers and Finance.** It works for both stages (the request, and the settlement review by Finance). Only the person whose turn it is can approve.

Body: `{ "claim_no": "TRQ-2026-0001" }`

Response `200`:
```json
{ "claim_no": "TRQ-2026-0001", "status": "pending_approval",
  "next_approver": { "emp_code": "NX-1108", "name": "Meera Krishnan", "role": "Head of Department" } }
```
`status` is the claim's state after this approval. `next_approver` is null when this was the last step of the stage.

What each approval does:

| Who approves | Result |
|---|---|
| a manager who is not last | next manager is told |
| the last manager, advance requested | status `awaiting_advance`, Ravi is told to release it |
| the last manager, no advance | status `awaiting_settlement`, the employee is told to upload bills |
| Ravi, releasing the advance | advance recorded, status `awaiting_settlement` |
| Ravi, verifying a settlement | Kavitha is told to release the payout |
| Kavitha | status `paid`, the employee is told the amount is dispatched |

Errors: `403` not your claim / no approval is waiting on you / you cannot act on your own claim; `409` an earlier approver has not approved yet, or the claim has nothing to decide (`awaiting_settlement`, `paid`, `rejected`); `404` unknown claim.

### `POST /reject`
Reject a claim. Same rules as approve, but it closes the claim. **Screen: reject button with a reason box.**

Body: `{ "claim_no": "TRQ-2026-0002", "remarks": "Budget is over for this quarter" }` (`remarks` is required)

Response `200`: `{ "claim_no": "TRQ-2026-0002", "status": "rejected" }`
The claimant gets a notification with the reason. Errors are the same as `/approve`, plus `422` for empty `remarks`.

### `POST /upload_receipt`
Upload one receipt image for a claim in `awaiting_settlement`. **Screen: settlement page; call once per receipt.** Only the claim's owner can.

Send as `multipart/form-data`:

| Field | Value |
|---|---|
| `claim_no` | `TRQ-2026-0001` |
| `head` | what the receipt is for: `Travelling` (tickets, fuel, tolls), `Lodging`, `Meals`, `Business Entertainment`, `Local conveyance`, `Other`. The UI offers the ones that fit the claim type. |
| `file` | a PNG or JPEG, up to 5 MB |

What happens: the AI reads the image, we check it is not a repeat, then the AI checks the bill fits the `head`. The amount comes from the bill, the employee does not type it.

Response `200` when it matches (it will be counted):
```json
{ "line_id": 1, "head": "Business Entertainment", "status": "ok", "matched": true, "issue": null,
  "message": "Matches what you claimed. It will be counted.",
  "extracted": { "merchant": "SPICE TERRACE", "bill_no": "4471", "bill_date": "2026-06-18", "amount": "2255", "paid_by": "Employee",
                 "description": "Dinner at Spice Terrace", "items": ["2 x Paneer Tikka", "1 x Andhra Chicken", "4 x Butter Naan"] },
  "check": { "merchant_type": "restaurant", "matches": true, "issue": null } }
```
Response `200` when it does **not** match (it is flagged and not counted; the claimant and everyone who approved are notified):
```json
{ "line_id": 2, "head": "Local conveyance", "status": "excluded", "matched": false,
  "issue": "The bill is from a hotel for accommodation and dining, not a local conveyance provider.",
  "message": "The bill is from a hotel for accommodation and dining, not a local conveyance provider. It is flagged and not counted.",
  "extracted": { "merchant": "KEYS PRIME WHITEFIELD", "bill_no": "KPW/26-27/1188", "amount": "21504", "...": "..." },
  "check": { "merchant_type": "hotel", "matches": false, "issue": "..." } }
```

`status` values: `ok` (counted), `excluded` (did not match), `duplicate` (the same bill, same merchant / number / date / amount, was already uploaded on any claim; `check` is null). Show `message` to the user. Uploading the right receipt again is the way to fix an excluded one.
Errors: `403` not your claim; `409` the claim is not in `awaiting_settlement`; `413` over 5 MB; `415` not a PNG or JPEG; `502` / `503` the AI failed or is not set up (nothing is saved, the user can retry).

### `POST /submit_settlement`
Send the counted receipts to Finance. **Screen: "Submit settlement" button.** Needs at least one counted receipt paid by the employee.

Body: `{ "claim_no": "TRQ-2026-0001" }`

Response `200`:
```json
{ "claim_no": "TRQ-2026-0001", "status": "settlement_review", "paid_by_employee": "2255.00",
  "advance": "20000.00", "payable": "0", "recoverable": "17745.00",
  "next_approver": { "emp_code": "NX-3305", "name": "Ravi Menon", "role": "Finance" } }
```
`payable` is what the company will pay the employee (receipts minus the advance). `recoverable` is what is deducted from the employee's payroll because the receipts are below the advance. At most one of the two is above zero.
Errors: `422` no counted receipt yet; `409` already submitted or wrong stage; `403` not your claim.

### `GET /get_claim_status?claim_no=TRQ-2026-0001`
Where is this claim now? **Screen: claim page.** Use it to decide what to show: for example, show the receipt upload only when the status is `awaiting_settlement`, and "Waiting for <name>" when it is `pending_approval`. Only the claim's owner, or someone on its approval list, may ask (anyone else gets `403`).

Response `200`:
```json
{ "claim_no": "TRQ-2026-0001", "status": "awaiting_settlement" }
```
`status` is one of the values in "The life of a claim" above. Errors: `404` unknown claim, `403` you are not involved in it.
It returns only the status. To say *who* the claim is waiting on, the UI still has to use the approvers returned by `create_claim` or `approve`.

### `GET /get_claim?claim_no=TRQ-2026-0001`
The whole claim, for the claim page. **One call redraws the page**: call it when the page opens and again after each upload, submit, approve or reject. The browser needs to remember nothing but the login. Only the claim's owner, or someone on its approval list, may read it (`403` otherwise, `404` unknown claim, `401` no headers).

Response `200` (shortened):
```json
{ "claim_no": "TRQ-2026-0002", "claimant_code": "NX-4471", "claimant_name": "Chaitanya Reddy",
  "template_name": "Travelling", "status": "settlement_review", "level": 2,
  "estimated_amount": "48000.00", "advance_requested": "20000.00", "advance_amount": "20000.00",
  "created_at": "2026-10-01T03:20:45",
  "fields": { "destination": "Bengaluru", "mode_of_transport": "Air", "number_of_days": 5, "...": "..." },
  "approvals": [
    { "name": "Suresh Iyer", "role": "Reporting Manager", "phase": "request", "step": 1, "action": "approve",
      "decision": "approved", "remarks": null, "decided_at": "2026-10-01T03:20:45" },
    { "name": "Ravi Menon", "role": "Finance", "phase": "settlement", "step": 1, "action": "verify",
      "decision": "pending", "remarks": null, "decided_at": null } ],
  "receipts": [
    { "line_id": 4, "head": "Business Entertainment", "status": "ok", "message": "Matches what you claimed. It will be counted.",
      "merchant": "SPICE TERRACE", "bill_no": "4471", "bill_date": "2026-06-18", "amount": "2255.00", "paid_by": "Employee" } ],
  "totals": { "paid_by_employee": "23759.00", "advance": "20000.00", "payable": "3759.00", "recoverable": "0" } }
```
- `fields`: the answers given on the request form.
- `advance_requested` is what the employee asked for; `advance_amount` is what Finance actually released (0 until then).
- `approvals`: every step of **both** stages, request first, each in order, including Finance. The settlement steps appear once the settlement is submitted. Show a check mark for `decision: "approved"`, the `remarks` for a reject.
- `receipts`: oldest first, including flagged (`excluded`) and `duplicate` ones. `message` is the same sentence `upload_receipt` returned, so a reloaded page reads exactly like the live one. Only `ok` receipts are counted.
- `totals`: `null` until the settlement is submitted, then the same numbers `submit_settlement` returned.

### `GET /get_receipt_image?line_id=4`
The photo of one uploaded bill (`line_id` is in each receipt of `get_claim`). **Screen: the bills on the claim page.** Who may open it: the claim's **owner**, **anyone on its approval list** (so Finance can check the invoice before verifying it), and the **admin**; everyone else gets `403`.
Response `200`: the image itself (`image/png` or `image/jpeg`), not JSON. `404` unknown bill, or the file is gone (for example after a server restart).
An `<img src>` cannot send the session headers, so the UI fetches it with them and shows it as an object URL (`apiImage()` in `ui/js/api.js`).

### `GET /get_my_claims`
The claims the logged-in employee raised, newest first. **Screen: dashboard "My claims" and the Claims page.** The UI does not need to remember claim numbers itself; ask this each time the page opens. A claim raised on another browser or device shows up too.

Response `200`:
```json
[ { "claim_no": "TRQ-2026-0002", "template_name": "Food", "level": 1, "status": "awaiting_settlement",
    "estimated_amount": "4000.00", "created_at": "2026-10-01T02:32:04" },
  { "claim_no": "TRQ-2026-0001", "template_name": "Travelling", "level": 2, "status": "pending_approval",
    "estimated_amount": "48000.00", "created_at": "2026-10-01T02:32:04" } ]
```
An employee with no claims gets `[]`. Only claims the user **raised** are listed (a manager's team claims are not included). `created_at` is UTC.

### Admin endpoints (`/admin/...`)
Read-only views of **everything**, for the Admin role only. Log in as `admin@nortexindustries.com` like anyone else. Any other user gets `403`, and no headers gets `401`. The admin has no claims of their own, so the normal endpoints return empty lists for them. Templates are not repeated here: the admin uses the same `GET /get_templates` and `GET /get_template_required_fields` as everyone.

| Endpoint | Returns |
|---|---|
| `GET /admin/users` | every employee, same shape as `/auth/me` |
| `GET /admin/claims` | every claim, newest first: `claim_no`, `claimant_code`, `claimant_name`, `template_name`, `level`, `status`, `estimated_amount`, `advance_amount`, `created_at` |
| `GET /admin/approvals` | every approval step, grouped by claim: `claim_no`, `phase`, `step`, `role`, `action`, `approver_code`, `approver_name`, `decision`, `remarks`, `decided_at` |
| `GET /admin/notifications` | every notification sent to anyone, newest first: `recipient_code`, `recipient_name`, `claim_no`, `message`, `is_read`, `created_at` |

The admin page in the UI (`admin.html`) shows these as five tabs (Users, Templates, Claims, Approvals, Notifications). Its "Create template" button is a **mock**: it opens a form that saves nothing.

### `GET /`
A welcome message, public, no headers. Useful only to check the server is up.

---

## 3. A typical session, in calls

**Employee:** `login` → `dashboard/me` → `get_templates` → `get_template_required_fields` → `create_claim` → (wait; poll `get_all_notifications`) → after "fully approved": `upload_receipt` (one per bill) → `submit_settlement` → final notification says the amount is dispatched.

**Manager:** `login` → `get_pending_approvals` (the queue, each claim with the reason) → `get_claim` and `get_receipt_image` to read the details and check the bills → `approve` or `reject`.

**Finance:** the same as a manager. Ravi sees "release the advance" and later "verify"; Kavitha sees "release the payout". Both use `approve`.

## 4. Not available yet (the UI will need some of these)

| Missing | Effect on the UI |
|---|---|
| mark notifications as read | `is_read` never changes |
| return a claim with remarks (send back for correction) | only approve or reject |
| edit or delete an uploaded receipt | a wrongly flagged receipt stays in the list as excluded |
| logout | the UI can just forget the token |
| creating or editing templates and users | the admin pages are read-only; the 'Create template' button is a mock |
| policy cuts on amounts | the paid amount is the full bill total: no hotel per-night cap, meal cap, laundry / mini-bar deductions or dinner attendee names |
