"""Create nortex.db with all tables, then load the employees and the three fixed templates.

    python -m scripts.init_db

Safe to run again: existing tables and people are left alone.
To start from scratch, delete nortex.db and run it again.
"""
import asyncio

from src.resources import Resources
from src.seeder.seeder import seed_admin, seed_employees, seed_passwords, seed_templates


async def main() -> None:
    async with Resources() as resources:  # opens the database (and creates the tables)
        with resources.session() as db:
            people = seed_employees(db) + seed_admin(db)
            seed_passwords(db)
            templates = seed_templates(db)
    print(f"Tables ready. Employees added: {people}. Templates added: {templates}")


if __name__ == "__main__":
    asyncio.run(main())
