"""Create nortex.db with all tables, then load the employees and the three fixed templates.

    python -m scripts.init_db

Safe to run again: existing tables and people are left alone.
To start from scratch, delete nortex.db and run it again.
"""
from src.database.db import SessionLocal, create_tables
from src.seeder.seeder import seed_admin, seed_employees, seed_passwords, seed_templates

if __name__ == "__main__":
    create_tables()
    with SessionLocal() as db:
        people = seed_employees(db) + seed_admin(db)
        seed_passwords(db)
        templates = seed_templates(db)
    print(f"Tables ready. Employees added: {people}. Templates added: {templates}")
