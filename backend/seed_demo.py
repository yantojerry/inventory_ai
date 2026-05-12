"""Seed demo inventory data only when the database is empty."""

from __future__ import annotations

from app.models import InventorySystem
from database import DatabaseManager
from demo import build_sample_items, seed_sales_history


def seed_if_empty() -> None:
    database = DatabaseManager()
    system = InventorySystem(database=database)
    try:
        if database.list_items():
            print("Demo database already has inventory data. Skipping seed.")
            return
        print("Demo database is empty. Adding sample inventory data...")
        system.add_items(build_sample_items())
        seed_sales_history(system)
        print("Demo data ready.")
    finally:
        database.close()


if __name__ == "__main__":
    seed_if_empty()
