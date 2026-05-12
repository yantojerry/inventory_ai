"""AI analysis API endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.ai.setup_chatbot import build_setup_chat_response
from app.auth import get_current_user, require_super_admin, require_task_access
from app.crud import build_ai_payload, get_system
from app.models import InventorySystem
from app.schemas import AiAnalysisResponse, IndustrySetupChatRequest, SetupChatResponse


router = APIRouter()


@router.get("/inventory/{sku}/ai", response_model=AiAnalysisResponse)
async def get_ai_analysis(
    sku: str,
    user: Dict[str, Any] = Depends(get_current_user),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        item = system.get_item(sku)
        require_task_access(user, item.industry, "ai_recommendations")
        return {
            "sku": item.sku,
            "industry": item.industry,
            "ai": build_ai_payload(item, system),
            "advisory_note": "AI-generated recommendations require human approval before action.",
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory service unavailable: {exc}") from exc


@router.post("/ai/industry-setup-chat", response_model=SetupChatResponse)
async def industry_setup_chat(
    request: IndustrySetupChatRequest,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    """Guide Super Admins through industry task/module setup."""
    try:
        available_tasks = system.database.list_task_modules()
        response = build_setup_chat_response(
            industry=request.industry,
            display_name=request.display_name,
            selected_tasks=request.selected_tasks,
            message=request.message,
            history=[message.model_dump() for message in request.history],
            available_tasks=available_tasks,
        )
        return {
            **response,
            "advisory_note": "AI setup guidance is advisory; Super Admins choose the final industry modules.",
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Setup assistant unavailable: {exc}") from exc
