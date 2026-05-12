"""Configuration-driven industry profiles for the inventory system.

The rest of the project should read rules from these dictionaries instead of
hard-coding retail, healthcare, manufacturing, or IT asset behavior.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv


_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(_BACKEND_DIR / ".env", override=False)


def normalize_industry_key(industry: str) -> str:
    """Normalize user-facing industry names into stable storage keys."""
    return industry.strip().lower().replace("-", "_").replace(" ", "_")


TASK_MODULES: Dict[str, Dict[str, Any]] = {
    "inventory_management": {
        "display_name": "Inventory Management",
        "description": "Create, update, search, and view stock records.",
        "category": "Operations",
    },
    "sales_transactions": {
        "display_name": "Sales and Stock Transactions",
        "description": "Record stock changes, sales, receipts, and adjustments.",
        "category": "Operations",
    },
    "stock_alerts": {
        "display_name": "Stock Alerts",
        "description": "Show low-stock, expiry, and workflow alerts.",
        "category": "Operations",
    },
    "demand_forecasting": {
        "display_name": "Demand Forecasting",
        "description": "Forecast future demand from transaction history.",
        "category": "AI",
    },
    "reorder_planning": {
        "display_name": "Reorder Planning",
        "description": "Recommend reorder decisions from stock and demand signals.",
        "category": "AI",
    },
    "anomaly_detection": {
        "display_name": "Anomaly Detection",
        "description": "Detect unusual stock movement or sales patterns.",
        "category": "AI",
    },
    "expiry_risk": {
        "display_name": "Expiry Risk",
        "description": "Assess expiry, warranty, or shelf-life risk.",
        "category": "AI",
    },
    "ai_recommendations": {
        "display_name": "AI Recommendations",
        "description": "Use the AI engine and setup chatbot for guided decisions.",
        "category": "AI",
    },
    "report_generation": {
        "display_name": "Report Generation",
        "description": "Export inventory and transaction reports.",
        "category": "Reporting",
    },
}


AI_FEATURE_TASK_MAP = {
    "demand_forecast": "demand_forecasting",
    "reorder": "reorder_planning",
    "anomaly_detection": "anomaly_detection",
    "expiry_risk": "expiry_risk",
}


BASE_TASKS = [
    "inventory_management",
    "sales_transactions",
    "stock_alerts",
    "ai_recommendations",
    "report_generation",
]


INDUSTRY_PROFILES: Dict[str, Dict[str, Any]] = {
    "retail": {
        "display_name": "Retail",
        "description": "Fast-moving finished goods with seasonal demand swings.",
        "fields": ["sku", "name", "category", "brand", "season", "barcode", "supplier"],
        "track_expiry": True,
        "track_batch": False,
        "ai_features": ["demand_forecast", "reorder", "anomaly_detection", "expiry_risk"],
        "workflow": {
            "minimum_stock": 20,
            "expiry_warning_days": 30,
            "reorder_review_required": True,
        },
        "dynamic_attributes": {
            "category": "general",
            "brand": "generic",
            "season": "all-year",
            "barcode": None,
            "supplier": "default_supplier",
        },
        "forecast": {
            "default_history_days": 30,
            "default_forecast_days": 7,
            "seasonality_weight": 1.15,
        },
        "reorder": {
            "lead_time_days": 5,
            "safety_stock_multiplier": 1.25,
            "minimum_order_quantity": 10,
        },
        "anomaly": {
            "z_score_threshold": 2.0,
            "minimum_points": 5,
        },
        "expiry": {
            "enabled": True,
            "warning_days": 30,
            "critical_days": 7,
        },
    },
    "healthcare": {
        "display_name": "Healthcare",
        "description": "Regulated stock with batch, expiry, and storage controls.",
        "fields": [
            "sku",
            "name",
            "category",
            "batch_number",
            "dosage_form",
            "storage_temperature",
            "prescription_required",
            "supplier",
        ],
        "track_expiry": True,
        "track_batch": True,
        "ai_features": ["demand_forecast", "reorder", "anomaly_detection", "expiry_risk"],
        "workflow": {
            "minimum_stock": 15,
            "expiry_warning_days": 90,
            "reorder_review_required": True,
        },
        "dynamic_attributes": {
            "category": "medical_supply",
            "batch_number": None,
            "dosage_form": None,
            "storage_temperature": "room_temperature",
            "prescription_required": False,
            "supplier": "approved_supplier",
        },
        "forecast": {
            "default_history_days": 60,
            "default_forecast_days": 14,
            "seasonality_weight": 1.05,
        },
        "reorder": {
            "lead_time_days": 10,
            "safety_stock_multiplier": 1.75,
            "minimum_order_quantity": 5,
        },
        "anomaly": {
            "z_score_threshold": 1.75,
            "minimum_points": 5,
        },
        "expiry": {
            "enabled": True,
            "warning_days": 90,
            "critical_days": 30,
        },
    },
    "manufacturing": {
        "display_name": "Manufacturing",
        "description": "Raw materials and components with longer supplier lead times.",
        "fields": [
            "sku",
            "name",
            "component_type",
            "machine_line",
            "supplier",
            "unit_of_measure",
            "quality_grade",
        ],
        "track_expiry": False,
        "track_batch": False,
        "ai_features": ["demand_forecast", "reorder", "anomaly_detection"],
        "workflow": {
            "minimum_stock": 100,
            "expiry_warning_days": None,
            "reorder_review_required": True,
        },
        "dynamic_attributes": {
            "component_type": "raw_material",
            "machine_line": None,
            "supplier": "primary_supplier",
            "unit_of_measure": "piece",
            "quality_grade": "standard",
        },
        "forecast": {
            "default_history_days": 90,
            "default_forecast_days": 21,
            "seasonality_weight": 1.0,
        },
        "reorder": {
            "lead_time_days": 15,
            "safety_stock_multiplier": 1.5,
            "minimum_order_quantity": 25,
        },
        "anomaly": {
            "z_score_threshold": 2.25,
            "minimum_points": 6,
        },
        "expiry": {
            "enabled": False,
            "warning_days": 180,
            "critical_days": 45,
        },
    },
    "it": {
        "display_name": "IT Asset Management",
        "description": "Hardware, software, licenses, and warranty-controlled assets.",
        "fields": [
            "sku",
            "name",
            "asset_tag",
            "device_type",
            "assigned_department",
            "license_type",
            "warranty_provider",
            "supplier",
        ],
        "track_expiry": True,
        "track_batch": False,
        "ai_features": ["demand_forecast", "reorder", "anomaly_detection", "expiry_risk"],
        "workflow": {
            "minimum_stock": 3,
            "expiry_warning_days": 60,
            "reorder_review_required": True,
        },
        "dynamic_attributes": {
            "asset_tag": None,
            "device_type": "workstation",
            "assigned_department": "unassigned",
            "license_type": "perpetual",
            "warranty_provider": "standard",
            "supplier": "approved_it_supplier",
        },
        "forecast": {
            "default_history_days": 120,
            "default_forecast_days": 30,
            "seasonality_weight": 1.0,
        },
        "reorder": {
            "lead_time_days": 20,
            "safety_stock_multiplier": 1.2,
            "minimum_order_quantity": 2,
        },
        "anomaly": {
            "z_score_threshold": 2.0,
            "minimum_points": 5,
        },
        "expiry": {
            "enabled": True,
            "warning_days": 60,
            "critical_days": 14,
        },
    },
}


# Some capstone writeups use INDUSTRY_CONFIG as the canonical name. Keeping this
# alias lets the rest of the code and documentation use either term.
INDUSTRY_CONFIG = INDUSTRY_PROFILES

INDUSTRY_ALIASES = {
    "it_asset": "it",
    "it_assets": "it",
    "it_asset_management": "it",
    "information_technology": "it",
}


def validate_industry(industry: str) -> str:
    """Return a normalized industry key or raise a helpful error."""
    normalized = normalize_industry_key(industry)
    normalized = INDUSTRY_ALIASES.get(normalized, normalized)
    if normalized not in INDUSTRY_PROFILES:
        choices = ", ".join(sorted(INDUSTRY_PROFILES))
        raise ValueError(f"Unsupported industry '{industry}'. Choose one of: {choices}.")
    return normalized


def get_industry_config(industry: str) -> Dict[str, Any]:
    """Return a defensive copy of the selected industry profile."""
    return deepcopy(INDUSTRY_PROFILES[validate_industry(industry)])


def get_dynamic_attribute_defaults(industry: str) -> Dict[str, Any]:
    """Return the dynamic attributes expected for an industry."""
    return get_industry_config(industry)["dynamic_attributes"]


def tasks_from_ai_features(ai_features: Iterable[str]) -> List[str]:
    """Convert legacy AI feature names into task/module keys."""
    tasks = list(BASE_TASKS)
    for feature in ai_features:
        task_key = AI_FEATURE_TASK_MAP.get(feature)
        if task_key and task_key not in tasks:
            tasks.append(task_key)
    return tasks


def normalize_task_keys(task_keys: Iterable[str]) -> List[str]:
    """Return supported task keys in a stable order without duplicates."""
    normalized: List[str] = []
    for key in task_keys:
        task_key = str(key).strip().lower().replace("-", "_").replace(" ", "_")
        if not task_key:
            continue
        if task_key not in TASK_MODULES:
            choices = ", ".join(sorted(TASK_MODULES))
            raise ValueError(f"Unsupported task/module '{key}'. Choose one of: {choices}.")
        if task_key not in normalized:
            normalized.append(task_key)
    return normalized


def ensure_profile_tasks(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure a profile exposes enabled task/module keys."""
    if "enabled_tasks" not in profile:
        profile["enabled_tasks"] = tasks_from_ai_features(profile.get("ai_features", []))
    return profile


def register_industry_profile(key: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Register or replace a runtime industry profile."""
    normalized = normalize_industry_key(key)
    profile_copy = deepcopy(profile)
    profile_copy["display_name"] = profile_copy.get("display_name") or normalized.replace("_", " ").title()
    profile_copy["description"] = profile_copy.get("description", "")
    profile_copy["fields"] = profile_copy.get("fields") or ["sku", "name", "category", "supplier"]
    profile_copy["track_expiry"] = bool(profile_copy.get("track_expiry", False))
    profile_copy["track_batch"] = bool(profile_copy.get("track_batch", False))
    profile_copy["workflow"] = profile_copy.get("workflow") or {
        "minimum_stock": 10,
        "expiry_warning_days": 30 if profile_copy["track_expiry"] else None,
        "reorder_review_required": True,
    }
    profile_copy["dynamic_attributes"] = profile_copy.get("dynamic_attributes") or {
        "category": "general",
        "supplier": "default_supplier",
    }
    profile_copy["forecast"] = profile_copy.get("forecast") or {
        "default_history_days": 30,
        "default_forecast_days": 7,
        "seasonality_weight": 1.0,
    }
    profile_copy["reorder"] = profile_copy.get("reorder") or {
        "lead_time_days": 7,
        "safety_stock_multiplier": 1.25,
        "minimum_order_quantity": 5,
    }
    profile_copy["anomaly"] = profile_copy.get("anomaly") or {
        "z_score_threshold": 2.0,
        "minimum_points": 5,
    }
    profile_copy["expiry"] = profile_copy.get("expiry") or {
        "enabled": profile_copy["track_expiry"],
        "warning_days": 30,
        "critical_days": 7,
    }
    task_source = (
        profile_copy["enabled_tasks"]
        if "enabled_tasks" in profile_copy
        else tasks_from_ai_features(profile_copy.get("ai_features", []))
    )
    profile_copy["enabled_tasks"] = normalize_task_keys(task_source)
    profile_copy["ai_features"] = [
        feature
        for feature, task_key in AI_FEATURE_TASK_MAP.items()
        if task_key in profile_copy["enabled_tasks"]
    ]
    INDUSTRY_PROFILES[normalized] = profile_copy
    return deepcopy(profile_copy)


def get_enabled_tasks(industry: str) -> List[str]:
    """Return enabled task/module keys for an industry profile."""
    profile = INDUSTRY_PROFILES[validate_industry(industry)]
    ensure_profile_tasks(profile)
    return list(profile.get("enabled_tasks", []))


for _profile in INDUSTRY_PROFILES.values():
    ensure_profile_tasks(_profile)
