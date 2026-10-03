"""Database set-up. SQLite only: one file, nortex.db, in the project root. The engine itself is created once, at startup, by
src.resources.Resources; this file only knows how to build it and how to hand each request a session."""
import warnings
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase

DB_FILE = Path(__file__).resolve().parents[2] / "nortex.db"

# SQLite stores decimals as floats and SQLAlchemy warns about it. Our money has 2 decimals, so it round-trips exactly.
warnings.filterwarnings("ignore", message=".*Decimal.*", category=Warning)


def make_engine():
    """A new engine for the database file. Resources calls this once; nothing else should."""
    engine = create_engine(f"sqlite:///{DB_FILE}")
    # SQLite ignores foreign keys unless told otherwise; switch them on so a bad emp_code or claim_no is rejected.
    event.listen(engine, "connect", lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"))
    return engine


def utc_now() -> datetime:
    """Current UTC time without a timezone, the form SQLite stores. Use this for every timestamp we save or compare."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    """FastAPI dependency: one database session per request, always closed afterwards."""
    from src.resources import Resources  # imported here because resources.py imports this file

    with Resources.get().session() as db:
        yield db


class Base(DeclarativeBase):
    """Parent of every table class in models.py."""


def create_tables(engine) -> None:
    """Create any table that does not exist yet. Safe to run repeatedly; it never touches existing data."""
    from src.database import models  # noqa: F401  (importing registers the tables on Base)

    Base.metadata.create_all(engine)

    # create_all never alters an existing table, so an older nortex.db gets the new column added here.
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(employees)")]
        if "password_hash" not in columns:
            connection.exec_driver_sql("ALTER TABLE employees ADD COLUMN password_hash VARCHAR(100)")
        claim_columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(claims)")]
        if "flow" not in claim_columns:
            connection.exec_driver_sql("ALTER TABLE claims ADD COLUMN flow JSON")
        if "current_step" not in claim_columns:
            connection.exec_driver_sql("ALTER TABLE claims ADD COLUMN current_step INTEGER NOT NULL DEFAULT 0")
