"""Database connection. SQLite only: one file, nortex.db, in the project root."""
import warnings
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_FILE = Path(__file__).resolve().parents[2] / "nortex.db"

# SQLite stores decimals as floats and SQLAlchemy warns about it. Our money has 2 decimals, so it round-trips exactly.
warnings.filterwarnings("ignore", message=".*Decimal.*", category=Warning)

engine = create_engine(f"sqlite:///{DB_FILE}")
SessionLocal = sessionmaker(bind=engine)


@event.listens_for(engine, "connect")
def enforce_foreign_keys(connection, _record):
    """SQLite ignores foreign keys unless told otherwise; switch them on so a bad emp_code or claim_no is rejected."""
    connection.execute("PRAGMA foreign_keys=ON")


def utc_now() -> datetime:
    """Current UTC time without a timezone, the form SQLite stores. Use this for every timestamp we save or compare."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    """FastAPI dependency: one database session per request, always closed afterwards."""
    with SessionLocal() as db:
        yield db


class Base(DeclarativeBase):
    """Parent of every table class in models.py."""


def create_tables() -> None:
    """Create any table that does not exist yet. Safe to run repeatedly; it never touches existing data."""
    from src.database import models  # noqa: F401  (importing registers the tables on Base)

    Base.metadata.create_all(engine)

    # create_all never alters an existing table, so an older nortex.db gets the new column added here.
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(employees)")]
        if "password_hash" not in columns:
            connection.exec_driver_sql("ALTER TABLE employees ADD COLUMN password_hash VARCHAR(100)")
