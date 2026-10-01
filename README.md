# Nortex travel reimbursement

A web app that takes a business trip from **request** to **payout**: the manager chain approves it by amount, Finance releases the advance, the employee uploads photos of bills, an AI reads each bill and checks it matches what was claimed, and Finance pays out. The employee always sees where the claim is and who has it.

## Demo

**▶ [Watch the demo video (3 min 51 s)](video/demo.mp4)**

**Live app: <https://nortex-reimbursement-production.up.railway.app/>**

Log in with any account below. The password for all of them is `nortex123`.

| Email | Role | What to try |
|---|---|---|
| `chaitanya.reddy@nortexindustries.com` | Employee | Raise a trip or a meal claim, upload bills |
| `suresh.iyer@nortexindustries.com` | Reporting Manager | First approver for the sales team |
| `meera.krishnan@nortexindustries.com` | Head of Department | Second approver (claims above 25,000) |
| `arvind.rao@nortexindustries.com` | Head of Division | Third approver (claims above 75,000) |
| `nandita.shah@nortexindustries.com` | MD | Top approver (above 2,00,000 or international) |
| `ravi.menon@nortexindustries.com` | Finance | Releases advances, verifies settlements |
| `kavitha.balan@nortexindustries.com` | Finance Controller | Releases the payout |
| `admin@nortexindustries.com` | Admin | Read-only view of every user, template, claim, approval and notification |

Also in the data: Deepa Nair and Imran Qureshi (employees). To see the whole flow, use two browser windows, one signed in as the employee and one as the approver.

> The live site restarts empty whenever it is redeployed (see [Where it breaks](#where-it-breaks)), so any claim you make there is temporary.

## How it works

### One claim, start to finish

```mermaid
flowchart TD
    A(["Employee raises a request<br/>template, reason, amount, optional advance"]) --> B{"The amount<br/>decides the level"}
    B -->|"up to 25,000"| L1["L1: Reporting Manager"]
    B -->|"25,001 to 75,000"| L2["L2: plus Head of Department"]
    B -->|"75,001 to 2,00,000"| L3["L3: plus Head of Division"]
    B -->|"above 2,00,000 or international"| L4["L4: plus MD"]
    L1 --> C["Approvers decide one after another<br/>each is told only when it is their turn"]
    L2 --> C
    L3 --> C
    L4 --> C
    C -->|"anyone rejects"| X(["Rejected, the employee is told why"])
    C -->|"all approve"| D{"Advance<br/>asked for?"}
    D -->|yes| E["Finance (Ravi) releases the advance"]
    D -->|no| F
    E --> F["Employee takes the trip<br/>and uploads a photo of each bill"]
    F --> G["AI reads the bill, then checks it<br/>against what the employee claimed it was for"]
    G -->|"matches"| H["Counted"]
    G -->|"does not match"| I["Flagged and not counted<br/>employee and approvers are told"]
    G -->|"same bill again"| J["Duplicate, not counted"]
    H --> K["Employee submits the settlement"]
    K --> M["Finance (Ravi) verifies"]
    M --> N["Controller (Kavitha) releases the payout"]
    N --> O{"Counted bills<br/>vs the advance"}
    O -->|"bills are higher"| P(["Employee is paid the difference"])
    O -->|"bills are lower"| Q(["Difference is deducted from payroll"])
```

### What runs where

```mermaid
flowchart LR
    U["Browser<br/>HTML, CSS and JavaScript"] -->|"JSON over HTTP<br/>headers: emp-code and session-token"| API["FastAPI app<br/>(also serves the web pages)"]
    API --> DB[("SQLite<br/>nortex.db")]
    API --> FS["uploads/<br/>bill photos"]
    API -->|"bill image, then the claim check"| AI["Groq<br/>qwen3.8-27b"]
```

One container runs the whole thing on port 8000: the API and the web pages.

## The logic

**Who approves (L1 to L4).** The amount (the estimate for the request) picks the level. For that level the app lists the roles: the **Reporting Manager** is the person in the employee's `reporting_manager_code`; the **Head of Department** is the person with that role in the employee's department; there is one Head of Division and one MD. People who are missing, listed twice, or are the claimant themselves are dropped, so nobody approves their own claim (policy 2.2). The result is shown to the employee as a chain.

| Level | When | Approvers, in order |
|---|---|---|
| L1 | up to 25,000 | Reporting Manager |
| L2 | 25,001 to 75,000 | + Head of Department |
| L3 | 75,001 to 2,00,000 | + Head of Division |
| L4 | above 2,00,000, or any international trip | + MD |

**Advance.** At most 60% of the estimate; it is checked when the request is raised. Money is never released automatically: after the last manager approves, the claim goes to Finance (Ravi), who releases it.

**Bills.** Each photo (PNG or JPEG, up to 5 MB, checked by its real file type) goes through two AI calls on the same model:
1. *Read the bill*: it sees only the image and returns structured JSON (merchant, bill number, date, total, who paid, items). The employee's claim is deliberately not shown, so it cannot bias the reading.
2. *Check the claim*: it gets what the employee claimed (for example "Meals") and the JSON it just read, and says whether they fit.

A bill that does not fit is kept as **flagged** and not counted, and the employee and everyone who approved are told. The same bill (merchant, bill number, date, amount) uploaded again is marked **duplicate**.

**Money.** Only bills the employee paid for are reimbursed. `payable = bills − advance` if positive; otherwise `recoverable = advance − bills`, deducted from the next payroll. Payouts are scheduled for the next payment run, the 10th or 25th.

**Every claim states why.** Each template has a required "what is this for, and why is the money needed?" field. Approvers and Finance read it, and Finance can open the photo of every bill before verifying.

**Claim status** moves through: `pending_approval` → `awaiting_advance` → `awaiting_settlement` → `settlement_review` → `paid` (or `rejected`).

## Tech stack

| Part | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Fast to write, readable |
| API | FastAPI | Typed endpoints, automatic docs at `/docs` |
| Validation | Pydantic v2 | The AI's answers and every request are checked before they are trusted |
| Database | SQLAlchemy 2 with SQLite | One file, no server to run; money stored as exact decimals |
| AI | Groq, `qwen/qwen3.8-27b` (multimodal) | Reads bill photos and checks the claim, with JSON answers |
| UI | Plain HTML, CSS and JavaScript | No build step, easy to read and explain |
| Packaging | Docker | One command to run |
| Hosting | Railway | Runs the Docker image |

## Run it locally

You need a free Groq key from <https://console.groq.com/keys>. It is only used to read bills; the rest of the app works without it.

### With Docker

```bash
git clone <this repository>
cd Nortex-Industries-reimbursement-portal

docker build -t nortex-reimbursement .
docker run --rm -p 8000:8000 -e GROQ_API_KEY=your-key nortex-reimbursement
```

Open <http://localhost:8000>. Press Ctrl+C to stop it.

Or with Compose: `GROQ_API_KEY=your-key docker compose up --build`.

Or run the published image without cloning anything:

```bash
docker run --rm -p 8000:8000 -e GROQ_API_KEY=your-key bharathsimhareddy18/nortex-reimbursement:latest
```

### Without Docker

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=your-key
uvicorn main:app --reload
```

Open <http://localhost:8000>. The database file `nortex.db` is created on the first start, with the people and the three templates already loaded. To start over, stop the app and delete that file.

Interactive API docs are at <http://localhost:8000/docs>.

Run the tests with `pip install pytest && pytest`.

## Where things are

```
ui/            the web pages and their JavaScript
apis/          the endpoints (thin: they call into src/)
src/           the logic: claims, approvals, policy (who approves), settlement, ai, auth, admin
config/        policy numbers (setting.py) and the employee list
video/         the demo recording
api_docs.md    every endpoint with real example responses
data_model.md  the tables and the rules behind them
```

## Where it breaks

This is a working demo, not a finished product. In plain terms:

- **Policy cuts are not applied yet.** Bills are paid in full. There is no hotel per-night cap, no daily meal cap, no removal of laundry or mini-bar lines from a hotel bill, no attendee names for hosted dinners, and no check for a bill in someone else's name. These rules are in the expense policy, and the app is structured so they can be added in the settlement step.
- **Emails are not read.** Bills come in as uploaded photos only (PNG or JPEG). The text receipts in the sample inbox (Uber, e-ticket, hotel folio mails) are not parsed.
- **No second round of business approvals** on the final claimed amount, and **no "send back with remarks"**: a claim is approved or rejected. The 7-day filing deadline is not enforced.
- **A claim by a Finance person** (for example Ravi's own expense) would stall, because the person assigned to verify it is the claimant.
- **The duplicate check spans all employees.** Two people with an identical ride that has no bill number would collide.
- **Demo-grade security.** Everyone shares one password and sessions are plain tokens in the database. A real deployment would use per-user logins, hashed secrets, a login rate limit, and expire sessions on logout. Every endpoint except login and `/health` needs a valid session (enforced for the whole app, with a test that fails if one is ever left open), and the API gives no cross-origin permission to other websites.
- **Data does not survive a restart.** SQLite and the uploaded photos live inside the container. Every redeploy starts empty.
- **Single server.** Only one automated test file (the login check above), no background jobs, no logging beyond the server output.

## More

- [api_docs.md](api_docs.md): the full API, with example requests and responses
- [data_model.md](data_model.md): tables, rules, and decisions
