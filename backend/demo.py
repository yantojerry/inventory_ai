"""Demo simulation for the AI-enabled dynamic inventory system."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pprint import pprint

from sqlalchemy.exc import SQLAlchemyError

from app.ai import InventoryAI
from app.models import InventoryItem, InventorySystem
from database import DEFAULT_DATABASE_URL, DatabaseManager


def build_sample_items() -> list[InventoryItem]:
    return [
        InventoryItem(
            sku="RTL-COF-001",
            name="Premium Ground Coffee 250g",
            industry="retail",
            stock_quantity=42,
            unit_cost=88.50,
            expiry_date=date.today() + timedelta(days=45),
            attributes={
                "category": "grocery",
                "brand": "BeanCraft",
                "season": "all-year",
                "barcode": "480000000001",
            },
        ),
        InventoryItem(
            sku="HC-MSK-010",
            name="Surgical Mask Box",
            industry="healthcare",
            stock_quantity=30,
            unit_cost=115.00,
            expiry_date=date.today() + timedelta(days=75),
            attributes={
                "batch_number": "BATCH-MSK-2026-A",
                "storage_temperature": "room_temperature",
                "prescription_required": False,
            },
        ),
        InventoryItem(
            sku="MFG-BLT-025",
            name="Stainless Bolt M8",
            industry="manufacturing",
            stock_quantity=220,
            unit_cost=3.25,
            attributes={
                "component_type": "fastener",
                "machine_line": "assembly-line-2",
                "unit_of_measure": "piece",
                "quality_grade": "A2",
            },
        ),
        InventoryItem(
            sku="IT-LAP-100",
            name="Business Laptop Pool",
            industry="it",
            stock_quantity=6,
            unit_cost=42000.00,
            expiry_date=date.today() + timedelta(days=50),
            attributes={
                "asset_tag": "POOL-LAPTOP",
                "device_type": "laptop",
                "assigned_department": "shared_services",
                "license_type": "subscription",
                "warranty_provider": "vendor_standard",
            },
        ),
    ]


def seed_sales_history(system: InventorySystem) -> None:
    sales_patterns = {
        "RTL-COF-001": [7, 6, 8, 9, 7, 11, 10, 35, 9, 8, 12, 11],
        "HC-MSK-010": [4, 5, 5, 6, 4, 7, 5, 6, 20, 7, 6, 8],
        "MFG-BLT-025": [18, 19, 21, 20, 22, 23, 21, 24, 23, 25, 24, 27],
        "IT-LAP-100": [1, 1, 0, 2, 1, 1, 4, 1, 1, 2, 1, 3],
    }

    start = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=12)
    for sku, quantities in sales_patterns.items():
        for offset, quantity in enumerate(quantities):
            system.database.save_transaction(
                sku=sku,
                transaction_type="sale",
                quantity=quantity,
                unit_price=None,
                transaction_date=start + timedelta(days=offset),
                notes="simulation history",
            )


def simulate() -> None:
    db_url = (
        os.getenv("INVENTORY_DATABASE_URL")
        or os.getenv("INVENTORY_DB_URL")
        or DEFAULT_DATABASE_URL
    )
    print("Starting AI-enabled dynamic inventory simulation...")
    print("Database: SQLAlchemy ORM using MySQL/XAMPP by default")
    print(f"Database URL: {db_url}")
    print()

    try:
        database = DatabaseManager(db_url=db_url, reset=True)
    except SQLAlchemyError as exc:
        print("Database connection failed.")
        print("Check the MySQL service or set INVENTORY_DATABASE_URL.")
        print("Example MySQL URL:")
        print("$env:INVENTORY_DATABASE_URL='mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3307/inventory_ai'")
        print(f"SQLAlchemy error: {exc}")
        return

    system = InventorySystem(database=database)

    print("Creating sample multi-industry items...")
    system.add_items(build_sample_items())
    seed_sales_history(system)

    print("\nRecording a live sale through the InventorySystem...")
    sale_result = system.sell_item(
        sku="RTL-COF-001",
        quantity=3,
        unit_price=149.00,
        notes="walk-in sale",
    )
    pprint(sale_result)

    print("\nCurrent stock report:")
    for item in system.stock_report():
        pprint(item)

    print("\nAI advisory analysis:")
    for item in system.stock_report():
        inventory_item = system.get_item(item["sku"])
        history = system.sales_history(sku=inventory_item.sku)
        ai = InventoryAI(inventory_item.industry)
        print(f"\nSKU: {inventory_item.sku} | {inventory_item.name}")
        pprint(ai.forecast_demand(history))
        pprint(ai.recommend_reorder(inventory_item, history))
        pprint(ai.anomaly_detection(history))
        pprint(ai.expiry_risk(inventory_item, history))
        pprint(system.workflow_alerts(inventory_item.sku))

    database.close()


if __name__ == "__main__":
    simulate()


# SAMPLE OUTPUT, abbreviated:
# Starting AI-enabled dynamic inventory simulation...
# Database: SQLAlchemy ORM with SQLite default and optional MySQL/XAMPP URL
#
# Recording a live sale through the InventorySystem...
# {'message': 'Sale recorded. AI recommendations are advisory only.', ...}
#
# Current stock report:
# {'sku': 'HC-MSK-010', 'industry': 'healthcare', 'stock_quantity': 30, ...}
# {'sku': 'IT-LAP-100', 'industry': 'it', 'stock_quantity': 6, ...}
# {'sku': 'MFG-BLT-025', 'industry': 'manufacturing', 'stock_quantity': 220, ...}
# {'sku': 'RTL-COF-001', 'industry': 'retail', 'stock_quantity': 39, ...}
#
# AI advisory analysis:
# SKU: RTL-COF-001 | Premium Ground Coffee 250g
# {'method': 'LinearRegression', 'daily_forecast': [14, 14, 15, ...], ...}
# {'decision': 'review_reorder', 'suggested_order_quantity': 48, ...}
# {'method': 'LinearRegression residual z-score', 'anomalies': [...], ...}
# {'method': 'LinearRegression expiry risk curve', 'risk_level': 'watch', ...}
# {'workflow': {'minimum_stock': 20, ...}, 'alerts': [...], ...}
