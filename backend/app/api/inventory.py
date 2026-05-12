"""Inventory, transaction, industry, and report API endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from app.ai import InventoryAI
from app.auth import (
    allowed_industries,
    get_current_user,
    require_industry_access,
    require_inventory_manager,
    require_super_admin,
    require_task_access,
)
from app.crud import (
    build_ai_payload,
    csv_response,
    get_system,
    inventory_row,
    serialize_transaction,
)
from app.models import InventoryItem, InventorySystem
from app.schemas import (
    IndustryCatalogResponse,
    IndustryConfigRequest,
    IndustryCreateRequest,
    IndustryOperationResponse,
    IndustryTasksRequest,
    HealthResponse,
    ItemRequest,
    ItemUpdateRequest,
    InventoryDetailResponse,
    InventoryListResponse,
    ItemMutationResponse,
    InventoryTransactionMutationResponse,
    SellRequest,
    SellResponse,
    TaskModulesResponse,
    TransactionRequest,
    TransactionListResponse,
    MessageResponse,
)
from config import (
    BASE_TASKS,
    get_enabled_tasks,
    get_industry_config,
    normalize_industry_key,
    normalize_task_keys,
    validate_industry,
)


router = APIRouter()


def filter_items_for_user(items: list[InventoryItem], user: Dict[str, Any]) -> list[InventoryItem]:
    industries = allowed_industries(user)
    if industries is None:
        return items
    return [
        item
        for item in items
        if item.industry in industries and "inventory_management" in get_enabled_tasks(item.industry)
    ]


def task_is_enabled_for_user(user: Dict[str, Any], industry: str, task_key: str) -> bool:
    if user["role"] == "super_admin":
        return True
    try:
        return task_key in get_enabled_tasks(industry)
    except ValueError:
        return False


def industry_profile_from_request(request: IndustryCreateRequest) -> tuple[str, Dict[str, Any], list[str]]:
    key = normalize_industry_key(request.key or request.display_name)
    task_keys = normalize_task_keys(request.task_keys or BASE_TASKS)
    track_expiry = request.track_expiry
    if track_expiry is None:
        track_expiry = "expiry_risk" in task_keys
    dynamic_attributes = request.dynamic_attributes or {
        "category": "general",
        "supplier": "default_supplier",
        "location": None,
    }
    fields = request.fields or ["sku", "name", *dynamic_attributes.keys()]
    fields = list(dict.fromkeys(["sku", "name", *fields]))
    workflow = {
        "minimum_stock": 10,
        "expiry_warning_days": 30 if track_expiry else None,
        "reorder_review_required": True,
        **request.workflow,
    }
    profile = {
        "display_name": request.display_name.strip(),
        "description": request.description.strip(),
        "fields": fields,
        "track_expiry": bool(track_expiry),
        "track_batch": bool(request.track_batch),
        "enabled_tasks": task_keys,
        "dynamic_attributes": dynamic_attributes,
        "workflow": workflow,
        "forecast": {
            "default_history_days": 30,
            "default_forecast_days": 7,
            "seasonality_weight": 1.0,
            **request.forecast,
        },
        "reorder": {
            "lead_time_days": 7,
            "safety_stock_multiplier": 1.25,
            "minimum_order_quantity": 5,
            **request.reorder,
        },
        "anomaly": {
            "z_score_threshold": 2.0,
            "minimum_points": 5,
            **request.anomaly,
        },
        "expiry": {
            "enabled": bool(track_expiry),
            "warning_days": 30,
            "critical_days": 7,
            **request.expiry,
        },
    }
    return key, profile, task_keys


@router.get("/health", response_model=HealthResponse)
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/inventory", response_model=InventoryListResponse)
async def list_inventory(
    industry: Optional[str] = None,
    search: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        if industry:
            industry = require_task_access(user, industry, "inventory_management")
        items = system.database.list_items(industry=industry) if system.database else []
        items = filter_items_for_user(items, user)
        if search:
            needle = search.strip().lower()
            items = [
                item
                for item in items
                if needle in item.sku.lower()
                or needle in item.name.lower()
                or any(needle in str(value).lower() for value in item.attributes.values())
            ]
        rows = [inventory_row(system, item) for item in items]
        return {"items": rows, "count": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.get("/inventory/{sku}", response_model=InventoryDetailResponse)
async def get_item(
    sku: str,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        item = system.get_item(sku)
        require_task_access(user, item.industry, "inventory_management")
        return {
            "item": item.to_dict(),
            "ai": build_ai_payload(item, system),
            "advisory_note": "AI output assists decisions and does not auto-control inventory.",
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.post("/inventory/sell", response_model=SellResponse)
async def sell_item(
    request: SellRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        item = system.get_item(request.sku)
        require_inventory_manager(user, item.industry)
        require_task_access(user, item.industry, "sales_transactions")
        result = system.sell_item(
            sku=request.sku,
            quantity=request.quantity,
            unit_price=request.unit_price,
            notes=request.notes,
        )
        updated_item = system.get_item(request.sku)
        history = system.sales_history(sku=updated_item.sku)
        ai = InventoryAI(updated_item.industry)
        result["ai_reorder_recommendation"] = ai.recommend_reorder(updated_item, history)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.post("/inventory/items", response_model=ItemMutationResponse)
async def add_item(
    request: ItemRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        require_inventory_manager(user, request.industry)
        item = InventoryItem(
            sku=request.sku,
            name=request.name,
            industry=request.industry,
            stock_quantity=request.stock_quantity,
            unit_cost=request.unit_cost,
            expiry_date=request.expiry_date,
            attributes=request.attributes,
        )
        system.add_item(item)
        return {
            "message": "Item added or updated.",
            "item": item.to_dict(),
            "workflow": system.workflow_alerts(item.sku),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.patch("/inventory/items/{sku}", response_model=ItemMutationResponse)
async def update_item(
    sku: str,
    request: ItemUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        item = system.get_item(sku)
        require_inventory_manager(user, item.industry)
        updates = request.model_dump(exclude_unset=True)
        if "name" in updates and updates["name"] is not None:
            item.name = updates["name"]
        if "stock_quantity" in updates and updates["stock_quantity"] is not None:
            item.stock_quantity = updates["stock_quantity"]
        if "unit_cost" in updates and updates["unit_cost"] is not None:
            item.unit_cost = updates["unit_cost"]
        if "expiry_date" in updates:
            item.expiry_date = updates["expiry_date"]
        if "attributes" in updates and updates["attributes"] is not None:
            item.attributes.update(updates["attributes"])
        require_inventory_manager(user, item.industry)
        system.add_item(item)
        return {
            "message": "Item updated.",
            "item": item.to_dict(),
            "workflow": system.workflow_alerts(item.sku),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.delete("/inventory/items/{sku}", response_model=MessageResponse)
async def delete_item(
    sku: str,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, str]:
    try:
        item = system.get_item(sku)
        require_inventory_manager(user, item.industry)
        if not system.database.delete_item(sku):
            raise KeyError(f"Item with SKU '{sku.strip().upper()}' was not found.")
        system.items.pop(sku.strip().upper(), None)
        return {"message": "Item deleted."}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.post("/inventory/transactions", response_model=InventoryTransactionMutationResponse)
async def record_inventory_transaction(
    request: TransactionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        item = system.get_item(request.sku)
        require_inventory_manager(user, item.industry)
        require_task_access(user, item.industry, "sales_transactions")
        if request.change == 0:
            raise ValueError("Transaction change cannot be zero.")
        item.adjust_stock(request.change)
        system.add_item(item)
        transaction_type = "sale" if request.change < 0 else "restock"
        transaction = system.database.save_transaction(
            sku=item.sku,
            transaction_type=transaction_type,
            quantity=abs(request.change),
            unit_price=request.unit_price,
            notes=request.reason,
        )
        return {
            "message": "Transaction recorded. AI recommendations remain advisory only.",
            "item": item.to_dict(),
            "transaction": serialize_transaction(transaction),
            "ai": build_ai_payload(item, system),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.get("/task-modules", response_model=TaskModulesResponse)
async def list_task_modules(
    _: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        tasks = system.database.list_task_modules()
        return {"task_modules": tasks, "count": len(tasks)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Task module service unavailable: {exc}") from exc


@router.get("/industries", response_model=IndustryCatalogResponse)
async def list_industries(
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        allowed = allowed_industries(user)
        records = system.database.list_industries()
        if allowed is not None:
            records = [record for record in records if record["key"] in allowed]
        industries = {record["key"]: record["profile"] for record in records}
        return {
            "industries": industries,
            "industry_records": records,
            "task_modules": system.database.list_task_modules(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Industry service unavailable: {exc}") from exc


@router.post("/industries", response_model=IndustryOperationResponse)
async def create_industry(
    request: IndustryCreateRequest,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        key, profile, task_keys = industry_profile_from_request(request)
        industry = system.database.create_industry(key, profile, task_keys)
        return {
            "message": "Industry created.",
            "industry": industry,
            "config": get_industry_config(key),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Industry service unavailable: {exc}") from exc


@router.put("/industries/{industry}/tasks", response_model=IndustryOperationResponse)
async def update_industry_tasks(
    industry: str,
    request: IndustryTasksRequest,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        key = validate_industry(industry)
        updated = system.database.update_industry_tasks(key, request.task_keys)
        return {
            "message": "Industry tasks updated.",
            "industry": updated,
            "config": get_industry_config(key),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Industry service unavailable: {exc}") from exc


@router.patch("/industries/{industry}/config", response_model=IndustryOperationResponse)
async def update_industry_config(
    industry: str,
    request: IndustryConfigRequest,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        key = validate_industry(industry)
        updates = request.model_dump(exclude_none=True)
        updated = system.database.update_industry_config(key, updates)
        return {"industry": updated, "config": get_industry_config(key)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Industry service unavailable: {exc}") from exc


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    sku: Optional[str] = None,
    transaction_type: Optional[str] = None,
    days: Optional[int] = None,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        transactions = system.database.query_transactions(
            sku=sku,
            transaction_type=transaction_type,
            days=days,
        )
        filtered = []
        for transaction in transactions:
            try:
                item = system.get_item(transaction["sku"])
                require_industry_access(user, item.industry)
                filtered.append(transaction)
            except (HTTPException, KeyError):
                continue
        rows = [serialize_transaction(transaction) for transaction in filtered]
        return {"transactions": rows, "count": len(rows)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction service unavailable: {exc}") from exc


@router.get("/reports/inventory.csv")
async def download_inventory_report(
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> StreamingResponse:
    try:
        rows = []
        for item in filter_items_for_user(system.database.list_items(), user):
            ai_payload = build_ai_payload(item, system)
            rows.append(
                {
                    "sku": item.sku,
                    "name": item.name,
                    "industry": item.industry,
                    "stock_quantity": item.stock_quantity,
                    "unit_cost": item.unit_cost,
                    "expiry_date": item.expiry_date.isoformat() if item.expiry_date else "",
                    "forecast_total": ai_payload["forecast"]["total_forecast"],
                    "reorder_decision": ai_payload["reorder"]["decision"],
                    "suggested_order_quantity": ai_payload["reorder"]["suggested_order_quantity"],
                    "expiry_risk": ai_payload["expiry_risk"]["risk_level"],
                    "workflow_alerts": len(ai_payload["workflow"]["alerts"]),
                }
            )
        return csv_response("inventory_ai_report.csv", rows)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation unavailable: {exc}") from exc


@router.get("/reports/transactions.csv")
async def download_transactions_report(
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> StreamingResponse:
    try:
        rows = []
        for transaction in system.database.query_transactions():
            try:
                item = system.get_item(transaction["sku"])
                require_industry_access(user, item.industry)
            except (HTTPException, KeyError):
                continue
            serialized = serialize_transaction(transaction)
            rows.append(
                {
                    "id": serialized["id"],
                    "sku": serialized["sku"],
                    "transaction_type": serialized["transaction_type"],
                    "quantity": serialized["quantity"],
                    "unit_price": serialized["unit_price"],
                    "transaction_date": serialized["transaction_date"],
                    "notes": serialized["notes"],
                }
            )
        return csv_response("inventory_transactions_report.csv", rows)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation unavailable: {exc}") from exc
