"""Industry setup assistant for Super Admin configuration workflows."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from config import BASE_TASKS, TASK_MODULES, normalize_industry_key, normalize_task_keys


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"


INDUSTRY_HINTS: Dict[str, Dict[str, Any]] = {
    "retail": {
        "keywords": ["retail", "store", "shop", "grocery", "ecommerce", "e-commerce"],
        "tasks": [
            "inventory_management",
            "sales_transactions",
            "stock_alerts",
            "demand_forecasting",
            "reorder_planning",
            "anomaly_detection",
            "expiry_risk",
            "ai_recommendations",
            "report_generation",
        ],
        "track_expiry": True,
        "track_batch": False,
        "dynamic_attributes": {
            "category": "general",
            "brand": "generic",
            "barcode": None,
            "supplier": "default_supplier",
            "location": None,
        },
        "workflow": {"minimum_stock": 20, "expiry_warning_days": 30, "reorder_review_required": True},
        "notes": [
            "Enable forecasting and reorder planning for fast-moving SKUs.",
            "Keep expiry risk on when the catalog includes food, cosmetics, or dated goods.",
            "Use anomaly detection to flag unusual sales spikes, shrinkage, or data-entry mistakes.",
        ],
    },
    "healthcare": {
        "keywords": ["health", "medical", "clinic", "hospital", "pharma", "pharmacy", "medicine"],
        "tasks": [
            "inventory_management",
            "sales_transactions",
            "stock_alerts",
            "demand_forecasting",
            "reorder_planning",
            "anomaly_detection",
            "expiry_risk",
            "ai_recommendations",
            "report_generation",
        ],
        "track_expiry": True,
        "track_batch": True,
        "dynamic_attributes": {
            "category": "medical_supply",
            "batch_number": None,
            "dosage_form": None,
            "storage_temperature": "room_temperature",
            "prescription_required": False,
            "supplier": "approved_supplier",
        },
        "workflow": {"minimum_stock": 15, "expiry_warning_days": 90, "reorder_review_required": True},
        "notes": [
            "Track batch and expiry data for traceability and recall workflows.",
            "Use stricter expiry warning windows for regulated stock.",
            "Keep report generation enabled for audits and compliance reviews.",
        ],
    },
    "manufacturing": {
        "keywords": ["manufacturing", "factory", "production", "raw material", "component", "assembly"],
        "tasks": [
            "inventory_management",
            "sales_transactions",
            "stock_alerts",
            "demand_forecasting",
            "reorder_planning",
            "anomaly_detection",
            "ai_recommendations",
            "report_generation",
        ],
        "track_expiry": False,
        "track_batch": False,
        "dynamic_attributes": {
            "component_type": "raw_material",
            "machine_line": None,
            "supplier": "primary_supplier",
            "unit_of_measure": "piece",
            "quality_grade": "standard",
        },
        "workflow": {"minimum_stock": 100, "expiry_warning_days": None, "reorder_review_required": True},
        "notes": [
            "Prioritize reorder planning because supplier lead times are usually longer.",
            "Use anomaly detection to catch abnormal consumption by production line.",
            "Add batch tracking if quality inspection or recall traceability is required.",
        ],
    },
    "it": {
        "keywords": ["it", "asset", "license", "software", "hardware", "laptop", "device"],
        "tasks": [
            "inventory_management",
            "sales_transactions",
            "stock_alerts",
            "demand_forecasting",
            "reorder_planning",
            "anomaly_detection",
            "expiry_risk",
            "ai_recommendations",
            "report_generation",
        ],
        "track_expiry": True,
        "track_batch": False,
        "dynamic_attributes": {
            "asset_tag": None,
            "device_type": "workstation",
            "assigned_department": "unassigned",
            "license_type": "perpetual",
            "warranty_provider": "standard",
            "supplier": "approved_it_supplier",
        },
        "workflow": {"minimum_stock": 3, "expiry_warning_days": 60, "reorder_review_required": True},
        "notes": [
            "Use expiry risk for warranties, contracts, and software licenses.",
            "Keep anomaly detection on for unexpected device movement or license changes.",
            "Add department or asset-tag attributes before importing assets.",
        ],
    },
    "food_service": {
        "keywords": ["food", "restaurant", "cafe", "kitchen", "catering", "bakery"],
        "tasks": [
            "inventory_management",
            "sales_transactions",
            "stock_alerts",
            "demand_forecasting",
            "reorder_planning",
            "anomaly_detection",
            "expiry_risk",
            "ai_recommendations",
            "report_generation",
        ],
        "track_expiry": True,
        "track_batch": True,
        "dynamic_attributes": {
            "category": "ingredient",
            "batch_number": None,
            "storage_temperature": "chilled",
            "supplier": "approved_supplier",
            "location": "main_kitchen",
        },
        "workflow": {"minimum_stock": 25, "expiry_warning_days": 14, "reorder_review_required": True},
        "notes": [
            "Expiry and batch tracking are important for perishable ingredients.",
            "Forecasting helps prepare for day-of-week and seasonal demand.",
            "Use alerts for both low stock and near-expiry items.",
        ],
    },
}


def build_setup_chat_response(
    industry: str,
    display_name: Optional[str],
    selected_tasks: Iterable[str],
    message: str,
    history: Iterable[Dict[str, str]],
    available_tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return AI-assisted setup guidance with deterministic local fallbacks."""
    selected = _normalize_selected_tasks(selected_tasks)
    effective_industry, effective_display_name = _resolve_industry_context(industry, display_name, message, history)
    recommendation = recommend_industry_setup(effective_industry, effective_display_name, selected)
    recommendation_ready = _has_industry_context(effective_industry, effective_display_name) and not _is_casual_message(message)
    if recommendation_ready:
        prompt = _build_prompt(
            effective_industry,
            effective_display_name,
            selected,
            message,
            history,
            available_tasks,
            recommendation,
        )
        provider_response = _call_configured_provider(prompt)
    else:
        provider_response = {"provider": "local", "content": None}
    reply = provider_response.get("content") or _local_reply(
        recommendation,
        selected,
        message,
        industry=effective_industry,
        display_name=effective_display_name,
        provider_response=provider_response,
    )

    return {
        "provider": provider_response.get("provider", "local"),
        "used_external_ai": bool(provider_response.get("content")),
        "provider_error": provider_response.get("error"),
        "recommendation_ready": recommendation_ready,
        "inferred_industry": effective_industry,
        "inferred_display_name": effective_display_name,
        "reply": reply,
        "recommended_task_keys": recommendation["recommended_task_keys"],
        "selected_task_keys": selected,
        "add_task_keys": recommendation["add_task_keys"],
        "review_task_keys": recommendation["review_task_keys"],
        "recommended_config": recommendation["recommended_config"],
        "setup_hints": recommendation["setup_hints"],
        "follow_up_questions": recommendation["follow_up_questions"],
    }


def recommend_industry_setup(
    industry: str,
    display_name: Optional[str],
    selected_tasks: Iterable[str],
) -> Dict[str, Any]:
    """Recommend modules and baseline settings from the industry label."""
    selected = _normalize_selected_tasks(selected_tasks)
    profile = _match_profile(industry, display_name)
    recommended_tasks = normalize_task_keys(profile["tasks"])
    missing = [task for task in recommended_tasks if task not in selected]
    review = [
        task
        for task in selected
        if task not in recommended_tasks and task not in {"inventory_management", "report_generation"}
    ]

    config = {
        "track_expiry": bool(profile["track_expiry"]),
        "track_batch": bool(profile["track_batch"]),
        "dynamic_attributes": profile["dynamic_attributes"],
        "workflow": profile["workflow"],
        "forecast": {
            "default_history_days": 60 if normalize_industry_key(industry or display_name or "") == "healthcare" else 30,
            "default_forecast_days": 14 if profile["track_batch"] else 7,
            "seasonality_weight": 1.0,
        },
        "reorder": {
            "lead_time_days": 10 if profile["track_batch"] else 7,
            "safety_stock_multiplier": 1.5 if profile["track_batch"] else 1.25,
            "minimum_order_quantity": 5,
        },
        "anomaly": {"z_score_threshold": 2.0, "minimum_points": 5},
        "expiry": {
            "enabled": bool(profile["track_expiry"]),
            "warning_days": profile["workflow"].get("expiry_warning_days") or 30,
            "critical_days": 7,
        },
    }

    return {
        "matched_profile": profile["key"],
        "recommended_task_keys": recommended_tasks,
        "add_task_keys": missing,
        "review_task_keys": review,
        "recommended_config": config,
        "setup_hints": profile["notes"],
        "follow_up_questions": [
            "Does this industry require expiry, warranty, or license-date tracking?",
            "Do items need batch or lot numbers for recalls, audits, or quality checks?",
            "What minimum stock threshold and supplier lead time should be used by default?",
        ],
    }


def _normalize_selected_tasks(selected_tasks: Iterable[str]) -> List[str]:
    try:
        return normalize_task_keys(selected_tasks)
    except ValueError:
        supported = [task for task in selected_tasks if str(task).strip().lower().replace("-", "_").replace(" ", "_") in TASK_MODULES]
        return normalize_task_keys(supported)


def _match_profile(industry: str, display_name: Optional[str]) -> Dict[str, Any]:
    text = f"{industry} {display_name or ''}".strip().lower()
    normalized = normalize_industry_key(text or "general")
    best_key = "retail"
    best_score = 0
    for key, profile in INDUSTRY_HINTS.items():
        score = 2 if key in normalized else 0
        score += sum(1 for keyword in profile["keywords"] if keyword in text)
        if score > best_score:
            best_key = key
            best_score = score
    profile = dict(INDUSTRY_HINTS[best_key])
    profile["key"] = best_key
    return profile


def _resolve_industry_context(
    industry: str,
    display_name: Optional[str],
    message: str,
    history: Iterable[Dict[str, str]],
) -> tuple[str, Optional[str]]:
    if _has_industry_context(industry, display_name):
        return industry, display_name

    profile_key = _detect_profile_key(message)
    if profile_key:
        profile = INDUSTRY_HINTS[profile_key]
        return profile_key, str(profile_key).replace("_", " ").title()

    for chat_message in reversed(list(history)[-6:]):
        if chat_message.get("role") != "user":
            continue
        profile_key = _detect_profile_key(chat_message.get("content", ""))
        if profile_key:
            return profile_key, str(profile_key).replace("_", " ").title()

    return industry, display_name


def _detect_profile_key(text: str) -> Optional[str]:
    normalized_text = normalize_industry_key(text or "")
    raw_text = (text or "").strip().lower()
    if not raw_text:
        return None
    for key, profile in INDUSTRY_HINTS.items():
        if normalized_text == key:
            return key
        if any(keyword in raw_text for keyword in profile["keywords"]):
            return key
    return None


def _has_industry_context(industry: str, display_name: Optional[str]) -> bool:
    context = f"{industry or ''} {display_name or ''}".strip()
    if not context:
        return False
    normalized = normalize_industry_key(context)
    return normalized not in {"general", "new_industry", "industry", "draft"}


def _is_casual_message(message: str) -> bool:
    normalized = message.strip().lower().strip(".!?")
    return normalized in {
        "hi",
        "hello",
        "hey",
        "yo",
        "good morning",
        "good afternoon",
        "good evening",
    }


def _is_uncertain_message(message: str) -> bool:
    normalized = message.strip().lower().strip(".!?")
    return normalized in {
        "i dont know",
        "i don't know",
        "not sure",
        "unsure",
        "idk",
        "no idea",
    }


def _build_prompt(
    industry: str,
    display_name: Optional[str],
    selected_tasks: List[str],
    message: str,
    history: Iterable[Dict[str, str]],
    available_tasks: List[Dict[str, Any]],
    recommendation: Dict[str, Any],
) -> str:
    task_summary = [
        {
            "key": task["key"],
            "display_name": task["display_name"],
            "description": task.get("description", ""),
            "category": task.get("category", "General"),
        }
        for task in available_tasks
    ]
    recent_history = list(history)[-6:]
    payload = {
        "industry": industry,
        "display_name": display_name,
        "selected_tasks": selected_tasks,
        "local_recommendation": recommendation,
        "recent_history": recent_history,
        "super_admin_message": message,
    }
    return (
        "You are an inventory-system setup assistant. Help a Super Admin choose modules "
        "and baseline configuration for a new industry. Use only these task keys: "
        f"{', '.join(task['key'] for task in task_summary)}. "
        "Be concise, practical, and include any questions that affect the setup.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )


def _call_configured_provider(prompt: str) -> Dict[str, Any]:
    provider = os.getenv("AI_CHATBOT_PROVIDER", "auto").strip().lower()
    if provider in {"auto", "gemini"} and os.getenv("GEMINI_API_KEY"):
        response = _call_gemini(prompt)
        if response.get("content") or provider == "gemini":
            return response
    if provider in {"auto", "grok", "xai"} and (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")):
        response = _call_grok(prompt)
        if response.get("content") or provider in {"grok", "xai"}:
            return response
    return {"provider": "local", "content": None}


def _call_gemini(prompt: str) -> Dict[str, Any]:
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"{GEMINI_ENDPOINT.format(model=model)}?key={os.environ['GEMINI_API_KEY']}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.35, "maxOutputTokens": 350},
    }
    try:
        data = _post_json(url, payload)
        candidates = data.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        content = "\n".join(part.get("text", "") for part in parts).strip()
        return {"provider": "gemini", "content": content or None}
    except Exception as exc:
        return {"provider": "gemini", "content": None, "error": str(exc)}


def _call_grok(prompt: str) -> Dict[str, Any]:
    api_key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
    model = os.getenv("GROK_MODEL", "grok-4.3")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are an inventory-system setup assistant for Super Admins.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 700,
    }
    try:
        data = _post_json(GROK_ENDPOINT, payload, headers={"Authorization": f"Bearer {api_key}"})
        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content", "").strip() if choices else ""
        return {"provider": "grok", "content": content or None}
    except Exception as exc:
        return {"provider": "grok", "content": None, "error": str(exc)}


def _post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider returned HTTP {exc.code}: {detail}") from exc


def _local_reply(
    recommendation: Dict[str, Any],
    selected_tasks: List[str],
    message: str,
    industry: str = "",
    display_name: Optional[str] = None,
    provider_response: Optional[Dict[str, Any]] = None,
) -> str:
    provider_error = (provider_response or {}).get("error")
    provider_note = ""
    if provider_error:
        provider_note = (
            f" Gemini is configured, but the provider request failed: {provider_error[:240]}. "
            "I will use local setup guidance until that is fixed. "
        )

    if not _has_industry_context(industry, display_name):
        if _is_uncertain_message(message):
            return (
                f"{provider_note}No problem. Pick the closest industry first: retail for stores, "
                "healthcare for medical supplies or pharmacy, food service for restaurants, "
                "manufacturing for raw materials, IT assets for devices or licenses, or logistics "
                "for warehouse and delivery stock. You can also type a custom industry name."
            )
        return (
            f"{provider_note}What industry are you adding? For example: retail, healthcare, "
            "food service, manufacturing, IT assets, or logistics. Once I know that, I can "
            "recommend the best modules and baseline settings."
        )

    if _is_casual_message(message):
        return (
            f"{provider_note}Hi. I can help configure {display_name or industry}. Ask me which "
            "modules to enable, or tell me details like whether the stock expires, needs batch "
            "tracking, or has long supplier lead times."
        )

    recommended = ", ".join(recommendation["recommended_task_keys"])
    missing = ", ".join(recommendation["add_task_keys"]) or "none"
    hints = " ".join(recommendation["setup_hints"])
    expiry_note = (
        "Expiry tracking should be enabled."
        if recommendation["recommended_config"]["track_expiry"]
        else "Expiry tracking is optional unless items have shelf-life, warranty, or license dates."
    )
    batch_note = (
        "Batch tracking is recommended for traceability."
        if recommendation["recommended_config"]["track_batch"]
        else "Batch tracking can stay off unless audit or recall traceability is required."
    )
    return (
        f"{provider_note}Recommended modules: {recommended}. Missing from the current selection: {missing}. "
        f"{expiry_note} {batch_note} {hints}"
    )
