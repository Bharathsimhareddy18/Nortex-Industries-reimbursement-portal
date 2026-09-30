# Data model and rules (design, nothing built yet)

SQLAlchemy on SQLite only (one file, `nortex.db`). Money is `NUMERIC(12,2)` (Decimal in Python, never float).
Fixed policy numbers live in `config/setting.py`. All logic lives in `src/`; `apis/` only calls it.

## One identifier per thing

| Thing | Identifier | Why |
|---|---|---|
| Employee | `emp_code` (NX-4471) | the CSV, the mails and every rule already talk in codes |
| Claim | `claim_no` (TRQ-2026-0001) | policy 1.1: everything is tracked against the Travel Request ID |

Other tables point to these two columns directly. There is no separate numeric `id` for employees or claims.

## Tables (7)

```sql
CREATE TABLE employees (
    emp_code                VARCHAR(20)  PRIMARY KEY,                -- NX-4471
    name                    VARCHAR(100) NOT NULL,
    email                   VARCHAR(100) NOT NULL UNIQUE,            -- login identity
    designation             VARCHAR(100),
    department              VARCHAR(50),                             -- used to find the Head of Department
    cost_centre             VARCHAR(20),
    city                    VARCHAR(50),
    reporting_manager_code  VARCHAR(20) REFERENCES employees(emp_code),   -- NULL for the MD
    role                    VARCHAR(30)  NOT NULL     -- Employee, Reporting Manager, Head of Department,
);                                                    -- Head of Division, MD, Finance, Admin

CREATE TABLE categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    VARCHAR(100) NOT NULL UNIQUE,             -- Domestic travel
    config  JSON NOT NULL                             -- that category's rules
);

CREATE TABLE claims (                                 -- one row per trip, updated through every stage
    claim_no          VARCHAR(20) PRIMARY KEY,        -- TRQ-2026-0001
    employee_code     VARCHAR(20) NOT NULL REFERENCES employees(emp_code),
    category_id       INTEGER NOT NULL REFERENCES categories(id),
    status            VARCHAR(25) NOT NULL,           -- pending_approval, awaiting_settlement,
                                                      -- settlement_review, paid, returned, rejected
    level             INTEGER NOT NULL,               -- L1..L4 of the current phase
    details           JSON NOT NULL,                  -- request form answers (purpose, destination, dates, advance asked...)
    estimated_amount  NUMERIC(12,2) NOT NULL,
    advance_amount    NUMERIC(12,2) NOT NULL DEFAULT 0,
    payment_date      DATE,
    created_at        DATETIME NOT NULL
);

CREATE TABLE lines (                                  -- rows of the Settlement Form, each with its proof
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_no          VARCHAR(20) NOT NULL REFERENCES claims(claim_no),
    section           VARCHAR(15) NOT NULL,           -- Lodging / Transport / Other
    head              VARCHAR(40) NOT NULL,           -- Lodging, Local conveyance, Meals, Business Entertainment...
    line_date         DATE,
    description       VARCHAR(300) NOT NULL,
    paid_by           VARCHAR(10) NOT NULL,           -- exactly 'Employee' or 'Company'
    amount            NUMERIC(12,2) NOT NULL,         -- what the bill says
    allowed           NUMERIC(12,2) NOT NULL,         -- what policy allows (disallowed = amount - allowed)
    reason            VARCHAR(300),                   -- why it was cut, or a note
    proof_ref         VARCHAR(100),                   -- bill / invoice number
    attendees         TEXT,                           -- names + organisation, for business entertainment
    file_path         VARCHAR(255),
    extracted         JSON,                           -- raw parsed / AI output
    merchant_category VARCHAR(30),                    -- restaurant, cab, hotel, fuel... from the classifier
    dedupe_key        VARCHAR(200),                   -- merchant|bill no|date|amount, to catch repeats
    status            VARCHAR(12) NOT NULL            -- ok, disallowed, duplicate, excluded
);

CREATE TABLE approvals (                              -- who must decide each phase, in order; also the audit trail
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_no       VARCHAR(20) NOT NULL REFERENCES claims(claim_no),
    phase          VARCHAR(12) NOT NULL,              -- request / settlement
    step           INTEGER NOT NULL,                  -- 1, 2, 3... order within the phase
    role           VARCHAR(30) NOT NULL,              -- the role this step is for, e.g. Head of Department, Finance
    action         VARCHAR(20) NOT NULL,              -- what this step is: approve | release_advance | verify | release_payment
    approver_code  VARCHAR(20) NOT NULL REFERENCES employees(emp_code),   -- the person asked to act on this step
    decision       VARCHAR(10) NOT NULL DEFAULT 'pending',   -- pending, approved, returned, rejected
    remarks        VARCHAR(500),
    decided_at     DATETIME
);

CREATE TABLE sessions (                               -- one row per login
    token       VARCHAR(64) PRIMARY KEY,              -- random, unguessable; sent with every request
    emp_code    VARCHAR(20) NOT NULL REFERENCES employees(emp_code),
    created_at  DATETIME NOT NULL,
    expires_at  DATETIME NOT NULL                     -- login time + session_hours (config/setting.py)
);

CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_code  VARCHAR(20) NOT NULL REFERENCES employees(emp_code),
    claim_no        VARCHAR(20) REFERENCES claims(claim_no),
    message         VARCHAR(500) NOT NULL,
    is_read         BOOLEAN NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL
);
```

## Who approves: the L1 to L4 rule

The level comes from the amount (or is L4 for any international trip), using `approval_bands` in `config/setting.py`.
The amount is the **estimate** for the request and the **net reimbursable claim** for the settlement.

| Level | When (domestic) | Candidates |
|---|---|---|
| L1 | up to 25,000 | Reporting Manager |
| L2 | 25,001 to 75,000 | + Head of Department |
| L3 | 75,001 to 2,00,000 | + Head of Division |
| L4 | above 2,00,000, or any international trip | + MD |

How the approvers for one claim are worked out (one function in `src`):

1. **Reporting Manager:** the person in the claimant's `reporting_manager_code`. The role text is not used for this.
2. **Head of Department:** the person whose role is Head of Department and whose `department` equals the claimant's department.
3. **Head of Division:** the person whose role is Head of Division (only one for now).
4. **MD:** the person whose role is MD.
5. Keep only the candidates that belong to the claim's level, in that order.
6. Remove the claimant, remove duplicates (keep the first), and skip any role nobody holds.
7. Finance steps are appended after the business approvers (policy 2.1) and are not part of L1 to L4 (see "Finance steps" below).

The claimant never approves their own claim (policy 2.2), which is what step 6 achieves.

| Claimant | L1 | L2 | L3 | L4 |
|---|---|---|---|---|
| Chaitanya, Deepa, Imran | Suresh | Suresh, Meera | + Arvind | + Nandita |
| Suresh | Meera | Meera | Meera, Arvind | Meera, Arvind, Nandita |
| Meera | Arvind | Arvind | Arvind | Arvind, Nandita |
| Arvind | Nandita | Nandita | Nandita | Nandita |
| Nandita (MD) | none | none | none | none (straight to Finance) |

This relies on: `department` and `reporting_manager_code` filled in for everyone, one Head of Division and one MD, and the first match being taken if a department ever has two heads.

## Finance steps

Three Finance steps exist. Each is a row in `approvals` with its own `action`. They never change, so they are written into each template's `config.finance_steps` (in `src/seeder/seeder.py`), together with the person: Ravi (NX-3305) for the advance and verification, Kavitha (NX-3300) for the payout. Only Travelling has the advance step; it has `only_if_positive: advance_requested`, so it exists only when the claim asks for an advance (no advance, no Finance step).

| Step | `action` | Person | Phase | Created when | What happens when it is done |
|---|---|---|---|---|---|
| Advance release | `release_advance` | Ravi (NX-3305) | request | at `create_claim`, as the last row after the approvers, only if an advance was requested. Ravi is **not** notified then, but when the last approver approves | `advance_amount` is set; claim becomes `awaiting_settlement` |
| Verification | `verify` | Ravi (NX-3305) | settlement | always (created when the settlement is filed; not built yet) | the claim moves to payout |
| Payout release | `release_payment` | Kavitha (NX-3300) | settlement | always | `payment_date` set to the next 10th/25th; claim becomes `paid` |

If the claimant is the person assigned to a Finance step, the next Finance user takes it (nobody acts on their own claim).
`claims.status` stays coarse; the exact current step is the first `pending` row in `approvals`.

## The flow

1. **Request** (before the trip). The employee raises a request with the estimate and optionally an advance (at most 60% of the estimate, policy 1.2). Status `pending_approval`; the first approver is notified, and each next approver is notified when the previous one approves.
2. **Approved.** After the last business approver: if an advance was requested, the **advance release** step goes to Ravi and the money is released only when he does it. If no advance was requested, this step does not exist and the claim goes straight to `awaiting_settlement`. Either way the employee is then told to upload bills. The advance is never paid automatically or before approval.
3. **Receipts.** Each file becomes settlement lines: not-an-expense mails and someone else's bills are excluded, repeats are marked duplicate, the rest are classified and priced by the policy rules.
4. **Settlement.** Blocked until every line has its proof and dinner attendees are given. Approvals run again by the net claim (L1 to L4), then Ravi verifies, then Kavitha releases the payout in the next 10th/25th run. Late filing (over 7 days after return) is a warning to approvers.
5. **Result.** Net claim minus advance: if positive it is payable to the employee; if negative the balance is recovered from the next payroll (policy 1.3).
6. **Return** (remarks required) sends the claim back to the employee with the same claim number; **reject** closes it.

## Visibility and permissions

- **Sees:** own claims plus everyone below them in the reporting chain. Finance and Admin see all.
- **Acts:** only on a step assigned to them, only when earlier steps are approved, never on their own claim.
- **Owner only:** upload documents, edit lines, file the settlement.
- **Admin only:** create users, create and edit categories.

## Login and sessions

`POST /auth/login` takes `{email, password}` (email is matched ignoring case and spaces; the password is the shared `demo_password` in `config/setting.py`). It saves a row in `sessions` and returns `{emp_code, session_token}`. Wrong email and wrong password give the same 401 message.
Every other endpoint needs two headers: `emp-code` and `session-token`. The session must exist, belong to that `emp_code`, and not be expired. Anything else is a 401, including missing headers.
No secret key is needed, because tokens are random values looked up in the table. Limits: old sessions are not cleaned up, there is no logout yet, and the token is stored as plain text.

## API (6 routers, 18 endpoints)

| Router | Endpoint | Why it exists |
|---|---|---|
| auth | `POST /auth/login` | email + shared demo password gives `emp_code` + `session_token` |
| | `GET /auth/me` | the UI learns the user's role |
| users | `GET /users` | public list for the login picker |
| | `POST /users` (admin) | add a person into the reporting chain |
| categories | `GET /categories` | choose a category, see its rules |
| | `POST /categories` (admin) | new category with its own rules |
| | `PUT /categories/{id}` (admin) | change the rules |
| claims | `POST /claims` | raise the request |
| | `GET /claims` | my / my team's / all claims |
| | `GET /claims/{claim_no}` | the Settlement Form data: lines, flags, approvals, totals |
| | `PATCH /claims/{claim_no}` | correct a returned request |
| | `POST /claims/{claim_no}/documents` | upload mails and receipts |
| | `PATCH /claims/{claim_no}/lines/{line_id}` | attendees, proof, head |
| | `POST /claims/{claim_no}/settle` | file the settlement |
| approvals | `GET /approvals` | my pending decisions |
| | `POST /approvals/{id}` | approve / return / reject |
| notifications | `GET /notifications` | my inbox |
| | `POST /notifications/read` | clear unread |

## Built so far

| Endpoint | What it does |
|---|---|
| `POST /auth/login` | email + demo password gives `emp_code` + `session_token` |
| `GET /auth/me` | full row of the logged-in person |
| `GET /dashboard/me` | `emp_code`, `email`, `designation`, `department`, `role` |
| `GET /get_templates` | `[{template_id, template_name}]` for the three templates |
| `GET /get_template_required_fields?template_id=&template_name=` | the fields that template asks for (id and name must both match) |
| `POST /create_claim` | `{template_id, fields}`; the claimant is the logged-in user |
| `POST /approve` | `{claim_no}`; the logged-in user approves their own pending step, in order |
| `POST /reject` | `{claim_no, remarks}`; same rules as approve, but the claim is closed as `rejected` and the claimant sees the reason |
| `GET /get_all_notifications` | the logged-in user's inbox, newest first |

All except login need the `emp-code` and `session-token` headers.

**Templates** are three rows in `categories` (ids 1 to 3), seeded by `src/seeder/seeder.py`; their field list is in `config.fields`. Fields are checked with a Pydantic model built from that list (required fields, types, limits, unknown fields rejected).

| Template | Fields |
|---|---|
| 1 Travelling | `destination`, `mode_of_transport` (Air/Train/Bus/Car), `number_of_days`, `departure_time`, `estimated_trip_cost`, optional `advance_requested` (default 0), optional `is_international` (default false) |
| 2 Food | `amount`, `city`, `city_tier` (1/2/3) |
| 3 Hotel stay | `hotel_name`, `city`, `city_tier` (1/2/3), `number_of_days` |

**`POST /create_claim`** (`src/claims/claims.py`, using `src/policy/policy.py` and `src/templates/templates.py`):
1. validate the fields; 2. work out the amount (Travelling: `estimated_trip_cost`; Food: `amount`; Hotel stay has no cost field, so **nights x the lodging limit of the tier**); 3. check the advance is at most 60% of it; 4. `Policy.get_level` gives L1 to L4 (any international trip is L4); 5. `Policy.get_approvers` lists the people for that level, dropping missing roles, repeats, and the claimant; 6. save the claim (`TRQ-year-number`), one `approvals` row per approver, and tell only the first approver.
With nobody to approve, the claim goes straight to `awaiting_settlement`.
Not built yet: the Finance advance-release step (it is added when the last approver approves), and the approve / return / reject endpoint.

## Decisions still open

1. **Base for the 60% advance cap.** Policy says employee-borne cost; the pack only gives a total estimate. Use the total estimate (simple), or ask the employee for the employee-borne split.
2. **In-room dining on a hotel folio.** Policy section 4 does not list dining, so the plan was to treat it as a meal under the daily limit, not disallow it.
3. **`emp_code` as the employees key** (no numeric `id`). Written that way above; confirm.

Decided: Ravi releases advances and verifies claims, Kavitha releases payouts (see "Finance steps").

## Not planned yet

Real auth (per-user passwords, token revocation), category versions, migrations (a reset script rebuilds the tables), `.xlsx` export of the form, partial-line approval.

## Approving (`POST /approve`)

`src/approvals/approvals.py`. Allowed only if: the caller is not the claimant, the claim is `pending_approval` or `awaiting_advance`, the caller has a pending request-stage step, and every earlier step is already approved (else 403 / 409).
On approval: the step is marked `approved`, the claimant is told, then
- another step follows: that person is told. If it is Finance's `release_advance` step, the claim becomes `awaiting_advance` and Ravi is asked to release the advance;
- nothing follows: the claim becomes `awaiting_settlement` and the claimant is told to upload bills. If the last step was the advance release, `advance_amount` is set from `advance_requested`.
`POST /reject` follows the same checks, but marks the step `rejected` (with the reason, which is required), sets the claim to `rejected` and tells the claimant. Steps after it stay `pending`, which is harmless because a rejected claim accepts no more decisions. Rejecting at Finance's advance step also rejects the whole claim.
Not built yet: return.
