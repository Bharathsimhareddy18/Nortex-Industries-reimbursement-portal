"""Create nortex.db with all tables and load the employees.

    python -m scripts.init_db

Safe to run again: existing tables and people are left alone.
To start from scratch, delete nortex.db and run it again.
"""
from src.database.db import SessionLocal, create_tables
from src.seeder.seeder import seed_employees

if __name__ == "__main__":
    create_tables()
    with SessionLocal() as db:
        added = seed_employees(db)
    print(f"Tables ready. Employees added: {added}")
