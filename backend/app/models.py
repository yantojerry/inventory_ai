"""Domain models for a configuration-driven inventory system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Dict, Iterable, List, Optional

from config import get_dynamic_attribute_defaults, get_industry_config, validate_industry


def utc_now() -> datetime:
    """Return naive UTC datetimes for broad SQL database compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class InventoryItem:
    """Inventory item with industry-specific dynamic attributes."""

    sku: str
    name: str
    industry: str
    stock_quantity: int
    unit_cost: float
    expiry_date: Optional[date] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.sku = self.sku.strip().upper()
        self.name = self.name.strip()
        self.industry = validate_industry(self.industry)
        self.stock_quantity = int(self.stock_quantity)
        self.unit_cost = float(self.unit_cost)

        if not self.sku:
            raise ValueError("Item SKU cannot be empty.")
        if not self.name:
            raise ValueError("Item name cannot be empty.")
        if self.stock_quantity < 0:
            raise ValueError("Stock quantity must be zero or greater.")
        if self.unit_cost <= 0:
            raise ValueError("Unit cost must be greater than zero.")

        defaults = get_dynamic_attribute_defaults(self.industry)
        merged_attributes = {**defaults, **self.attributes}
        self.attributes = merged_attributes

    @property
    def profile(self) -> Dict[str, Any]:
        return get_industry_config(self.industry)

    @property
    def inventory_value(self) -> float:
        return round(self.stock_quantity * self.unit_cost, 2)

    @property
    def days_to_expiry(self) -> Optional[int]:
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    def set_dynamic_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value
        self.updated_at = utc_now()

    def get_dynamic_attribute(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)

    def adjust_stock(self, delta: int) -> None:
        new_quantity = self.stock_quantity + int(delta)
        if new_quantity < 0:
            raise ValueError(
                f"Insufficient stock for {self.sku}: have {self.stock_quantity}, "
                f"attempted change {delta}."
        )
        self.stock_quantity = new_quantity
        self.updated_at = utc_now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "industry": self.industry,
            "stock_quantity": self.stock_quantity,
            "unit_cost": self.unit_cost,
            "inventory_value": self.inventory_value,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "days_to_expiry": self.days_to_expiry,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class InventorySystem:
    """High-level inventory operations.

    The system may run in memory for demos, but when a DatabaseManager is passed
    it persists items and transactions through the configured database manager.
    """

    def __init__(self, database: Any = None, ai_engine: Any = None) -> None:
        self.database = database
        self.ai_engine = ai_engine
        self.items: Dict[str, InventoryItem] = {}

    def add_item(self, item: InventoryItem, persist: bool = True) -> InventoryItem:
        self.items[item.sku] = item
        if persist and self.database:
            self.database.save_item(item)
        return item

    def add_items(self, items: Iterable[InventoryItem], persist: bool = True) -> None:
        for item in items:
            self.add_item(item, persist=persist)

    def get_item(self, sku: str) -> InventoryItem:
        normalized = sku.strip().upper()
        if normalized in self.items:
            return self.items[normalized]
        if self.database:
            item = self.database.query_item(normalized)
            if item:
                self.items[normalized] = item
                return item
        raise KeyError(f"Item with SKU '{normalized}' was not found.")

    def sell_item(
        self,
        sku: str,
        quantity: int,
        unit_price: Optional[float] = None,
        notes: str = "",
        persist: bool = True,
    ) -> Dict[str, Any]:
        item = self.get_item(sku)
        sale_quantity = int(quantity)
        if sale_quantity <= 0:
            raise ValueError("Sale quantity must be greater than zero.")

        item.adjust_stock(-sale_quantity)
        transaction = {
            "sku": item.sku,
            "transaction_type": "sale",
            "quantity": sale_quantity,
            "unit_price": unit_price,
            "transaction_date": utc_now(),
            "notes": notes,
        }

        if persist and self.database:
            self.database.save_item(item)
            self.database.save_transaction(**transaction)

        return {
            "message": "Sale recorded. AI recommendations are advisory only.",
            "item": item.to_dict(),
            "transaction": {
                **transaction,
                "transaction_date": transaction["transaction_date"].isoformat(),
            },
        }

    def record_transaction(
        self,
        sku: str,
        transaction_type: str,
        quantity: int,
        unit_price: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        item = self.get_item(sku)
        transaction = {
            "sku": item.sku,
            "transaction_type": transaction_type,
            "quantity": int(quantity),
            "unit_price": unit_price,
            "transaction_date": utc_now(),
            "notes": notes,
        }
        if self.database:
            self.database.save_transaction(**transaction)
        return transaction

    def sales_history(self, sku: Optional[str] = None, days: Optional[int] = None) -> List[Dict[str, Any]]:
        if self.database:
            return self.database.sales_history(sku=sku, days=days)
        return []

    def workflow_alerts(self, sku: str) -> Dict[str, Any]:
        """Return configurable, human-reviewed workflow alerts for an item."""
        item = self.get_item(sku)
        profile = item.profile
        workflow = profile.get("workflow", {})
        alerts = []

        minimum_stock = workflow.get("minimum_stock")
        if minimum_stock is not None and item.stock_quantity <= int(minimum_stock):
            alerts.append(
                {
                    "type": "minimum_stock",
                    "severity": "warning",
                    "message": (
                        f"{item.sku} has {item.stock_quantity} units, at or below "
                        f"the configured minimum of {minimum_stock}."
                    ),
                }
            )

        expiry_warning_days = workflow.get("expiry_warning_days")
        if expiry_warning_days is not None and item.days_to_expiry is not None:
            severity = "critical" if item.days_to_expiry <= 0 else "warning"
            if item.days_to_expiry <= int(expiry_warning_days):
                alerts.append(
                    {
                        "type": "expiry_warning",
                        "severity": severity,
                        "message": (
                            f"{item.sku} expires in {item.days_to_expiry} day(s); "
                            f"configured warning threshold is {expiry_warning_days} day(s)."
                        ),
                    }
                )

        return {
            "sku": item.sku,
            "industry": item.industry,
            "workflow": workflow,
            "alerts": alerts,
            "advisory_note": "Workflow alerts support review and do not automatically reorder or dispose stock.",
        }

    def stock_report(self) -> List[Dict[str, Any]]:
        if self.database:
            for item in self.database.list_items():
                self.items[item.sku] = item
        return [item.to_dict() for item in sorted(self.items.values(), key=lambda current: current.sku)]
