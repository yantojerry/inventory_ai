"""Shared database access and response helpers for API routes."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import StreamingResponse

from app.ai import InventoryAI
from app.models import InventoryItem, InventorySystem
from database import DatabaseManager


_database: Optional[DatabaseManager] = None
_inventory: Optional[InventorySystem] = None


def get_system() -> InventorySystem:
    global _database, _inventory

    if _database is None or _inventory is None:
        try:
            _database = DatabaseManager()
            _inventory = InventorySystem(database=_database)
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Database connection failed. Check the SQLite file path or "
                    f"INVENTORY_DATABASE_URL for MySQL/XAMPP. Error: {exc}"
                ),
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Database initialization failed: {exc}") from exc
    return _inventory


def close_database() -> None:
    global _database, _inventory

    if _database:
        _database.close()
    _database = None
    _inventory = None


def build_ai_payload(item: InventoryItem, system: InventorySystem) -> Dict[str, Any]:
    history = system.sales_history(sku=item.sku)
    ai = InventoryAI(item.industry)
    return {
        "forecast": ai.forecast_demand(history),
        "reorder": ai.recommend_reorder(item, history),
        "anomaly_detection": ai.anomaly_detection(history),
        "expiry_risk": ai.expiry_risk(item, history),
        "workflow": system.workflow_alerts(item.sku),
    }


def serialize_transaction(transaction: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **transaction,
        "transaction_date": transaction["transaction_date"].isoformat(),
    }


def inventory_row(system: InventorySystem, item: InventoryItem) -> Dict[str, Any]:
    ai_payload = build_ai_payload(item, system)
    return {
        "item": item.to_dict(),
        "ai": ai_payload,
        "workflow_alert_count": len(ai_payload["workflow"]["alerts"]),
    }


def csv_response(filename: str, rows: list[Dict[str, Any]]) -> StreamingResponse:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write("")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
