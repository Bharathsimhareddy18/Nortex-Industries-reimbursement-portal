# Nortex Industries travel reimbursement

An employee asks for a trip, managers approve it by amount, Finance releases an advance, the employee uploads photos of
bills, an AI reads each bill and checks it matches what was claimed, and Finance pays out. Everything (the API and the web
pages) runs as one app on port 8000.

## Run it (Docker, one command)

```
GROQ_API_KEY=your-key docker compose up --build
```

or create a file named `.env` in this folder containing one line, `GROQ_API_KEY=your-key`, and run `docker compose up --build`.

Open **http://localhost:8000** and log in.

- The key is never baked into the image; it is passed in when the container starts. It is only needed to read receipt photos. Without it the app still runs, and uploading a receipt says the key is not set.
- Prefer plain Docker? `docker build -t nortex .` then `docker run -p 8000:8000 -e GROQ_API_KEY=your-key nortex`.
- Data lives inside the container. `docker compose down` removes it and the next start begins fresh.

## Try it

Password for everyone: `nortex123`

| Log in as | Role |
|---|---|
| chaitanya.reddy@nortexindustries.com | Employee: raise the trip, upload receipts |
| suresh.iyer@nortexindustries.com | Reporting Manager: approves first |
| meera.krishnan@nortexindustries.com | Head of Department |
| ravi.menon@nortexindustries.com | Finance: releases the advance, verifies the claim |
| kavitha.balan@nortexindustries.com | Finance Controller: releases the payout |
| admin@nortexindustries.com | Admin: read-only view of every user, template, claim, approval and notification |

(Arvind Rao, Nandita Shah, Deepa Nair and Imran Qureshi also exist; see `api_docs.md`.)

Sample bills to upload are in the assessment pack's `receipts/` folder.

## Run it without Docker

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
echo 'GROQ_API_KEY=your-key' > .env
uvicorn main:app --reload   # http://localhost:8000
```

The database file `nortex.db` is created on first start, with the employees and the three templates loaded.

## Where things are

- `ui/` the web pages (plain HTML, CSS and JavaScript, no build step)
- `apis/` the endpoints; `src/` the logic behind them; `config/` the policy numbers and the employee list
- `api_docs.md` every endpoint, with real example responses; `data_model.md` the tables and the rules
