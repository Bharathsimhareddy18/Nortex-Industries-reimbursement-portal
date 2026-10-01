"""Loads the starting data. Only employees are seeded, from config/employee_master.csv."""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Category, Employee

CSV_PATH = Path(__file__).resolve().parents[2] / "config" / "employee_master.csv"
PLAIN_COLUMNS = ("emp_code", "name", "email", "designation", "department", "cost_centre", "city", "role")


# The one person who is not in the employee master: the admin who can look at everything (read-only). Same login as everyone.
ADMIN = dict(emp_code="NX-0001", name="Portal Admin", email="admin@nortexindustries.com", designation="System Administrator",
             department="Administration", cost_centre="CE900", city="Pune", role="Admin")


def seed_admin(db: Session) -> int:
    """Add the admin to the employees table if missing; returns 1 if it was added. Safe to run twice."""
    if db.get(Employee, ADMIN["emp_code"]):
        return 0
    db.add(Employee(**ADMIN))
    db.commit()
    return 1


def seed_employees(db: Session) -> int:
    """Insert the people who are not in the table yet; returns how many were added. Safe to run twice.

    Two passes: a manager can appear after their reports in the file, and the foreign key needs the manager row to exist first.
    """
    with CSV_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    existing = set(db.scalars(select(Employee.emp_code)))
    new_rows = [row for row in rows if row["emp_code"] not in existing]

    for row in new_rows:  # pass 1: everyone, without their manager link
        db.add(Employee(**{col: row[col].strip() or None for col in PLAIN_COLUMNS}))
    db.flush()

    for row in new_rows:  # pass 2: link each person to their reporting manager
        manager = row["reporting_manager_code"].strip()
        if manager:
            db.get(Employee, row["emp_code"]).reporting_manager_code = manager
    db.commit()
    return len(new_rows)


def _field(name, label, kind, required=True, **extra):
    """One field of a template. kind: text | integer | money | datetime | boolean | choice."""
    return {"name": name, "label": label, "type": kind, "required": required, **extra}


# Finance steps are part of the template because they never change. Ravi Menon (Manager, Finance Shared Services) releases advances
# and verifies claims; Kavitha Balan (Controller) releases the final payout. 'only_if_positive' names a field that must be above 0.
ADVANCE_STEP = {"phase": "request", "action": "release_advance", "emp_code": "NX-3305", "only_if_positive": "advance_requested"}
SETTLEMENT_STEPS = [
    {"phase": "settlement", "action": "verify", "emp_code": "NX-3305"},
    {"phase": "settlement", "action": "release_payment", "emp_code": "NX-3300"},
]

# The three fixed templates: name -> (fields, finance steps). Ids are assigned in this order: 1 Travelling, 2 Food, 3 Hotel stay.
TEMPLATES = {
    "Travelling": (
        [
            _field("destination", "Destination", "text"),
            _field("mode_of_transport", "Mode of transport", "choice", choices=["Air", "Train", "Bus", "Car"]),
            _field("number_of_days", "Number of days", "integer", min=1),
            _field("departure_time", "Departure time", "datetime"),
            _field("estimated_trip_cost", "Estimated trip cost", "money", min=0.01),
            _field("advance_requested", "Advance requested", "money", required=False, min=0, default=0),
            _field("is_international", "International trip", "boolean", required=False, default=False),
        ],
        [ADVANCE_STEP, *SETTLEMENT_STEPS],
    ),
    "Food": (
        [
            _field("amount", "Amount", "money", min=0.01),
            _field("city", "City", "text"),
            _field("city_tier", "City tier", "choice", choices=[1, 2, 3]),
        ],
        SETTLEMENT_STEPS,
    ),
    "Hotel stay": (
        [
            _field("hotel_name", "Hotel name", "text"),
            _field("city", "City", "text"),
            _field("city_tier", "City tier", "choice", choices=[1, 2, 3]),
            _field("number_of_days", "Number of days stayed", "integer", min=1),
        ],
        SETTLEMENT_STEPS,
    ),
}


def seed_templates(db: Session) -> int:
    """Create the fixed templates, or bring existing ones up to date with this file; returns how many changed.

    The three templates are defined in code, so the code wins. Templates an admin creates later have other names and are never touched.
    """
    existing = {c.name: c for c in db.scalars(select(Category))}
    changed = 0
    for name, (fields, finance_steps) in TEMPLATES.items():
        config = {"fields": fields, "finance_steps": finance_steps}
        if name not in existing:
            db.add(Category(name=name, config=config))
            changed += 1
        elif existing[name].config != config:
            existing[name].config = config
            changed += 1
    db.commit()
    return changed
