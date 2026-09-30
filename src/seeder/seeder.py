"""Loads the starting data. Only employees are seeded, from config/employee_master.csv."""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Employee

CSV_PATH = Path(__file__).resolve().parents[2] / "config" / "employee_master.csv"
PLAIN_COLUMNS = ("emp_code", "name", "email", "designation", "department", "cost_centre", "city", "role")


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
