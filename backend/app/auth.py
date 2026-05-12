"""JWT authentication and role-based access helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Iterable, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.crud import get_system
from app.models import InventorySystem
from config import get_enabled_tasks, validate_industry
from database import DatabaseManager


JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
JWT_EXPIRES_SECONDS = int(os.getenv("JWT_EXPIRES_SECONDS", "28800"))
ROLES = {"super_admin", "industry_admin", "user"}

bearer_scheme = HTTPBearer(auto_error=False)


def normalize_role(role: str) -> str:
    normalized = role.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in ROLES:
        choices = ", ".join(sorted(ROLES))
        raise ValueError(f"Unsupported role '{role}'. Choose one of: {choices}.")
    return normalized


def normalize_industries(industries: Iterable[str]) -> list[str]:
    return [validate_industry(industry) for industry in industries if str(industry).strip()]


def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password_hash"}


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def create_access_token(user: Dict[str, Any]) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "industries": user.get("industries", []),
        "iat": now,
        "exp": now + JWT_EXPIRES_SECONDS,
    }
    signing_input = ".".join(
        [
            _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        header, payload, signature = token.split(".", 2)
        signing_input = f"{header}.{payload}"
        expected = hmac.new(JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            raise ValueError("Invalid token signature.")
        data = json.loads(_b64decode(payload))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token.") from exc

    if int(data.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="Authentication token has expired.")
    return data


def authenticate_user(system: InventorySystem, username: str, password: str) -> Optional[Dict[str, Any]]:
    user = system.database.get_user_by_username(username, include_password=True)
    if not user or not user["is_active"]:
        return None
    if not DatabaseManager.verify_password(password, user["password_hash"]):
        return None
    return public_user(user)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Login required.")
    token_data = decode_access_token(credentials.credentials)
    user = system.database.get_user_by_id(int(token_data["sub"]))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User is inactive or no longer exists.")
    return user


def require_super_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin access required.")
    return user


def can_manage_inventory(user: Dict[str, Any]) -> bool:
    return user["role"] in {"super_admin", "industry_admin"}


def allowed_industries(user: Dict[str, Any]) -> Optional[list[str]]:
    if user["role"] == "super_admin":
        return None
    return user.get("industries", [])


def require_industry_access(user: Dict[str, Any], industry: str) -> str:
    normalized = validate_industry(industry)
    allowed = allowed_industries(user)
    if allowed is not None and normalized not in allowed:
        raise HTTPException(status_code=403, detail=f"You do not have access to {normalized} inventory.")
    return normalized


def require_task_access(user: Dict[str, Any], industry: str, task_key: str) -> str:
    """Require industry access and an enabled module for non-Super Admin users."""
    normalized = require_industry_access(user, industry)
    if user["role"] == "super_admin":
        return normalized
    if task_key not in get_enabled_tasks(normalized):
        raise HTTPException(status_code=403, detail=f"The {task_key} module is not enabled for {normalized}.")
    return normalized


def require_inventory_manager(user: Dict[str, Any], industry: str) -> str:
    if not can_manage_inventory(user):
        raise HTTPException(status_code=403, detail="Inventory changes require Industry Admin or Super Admin access.")
    return require_task_access(user, industry, "inventory_management")
