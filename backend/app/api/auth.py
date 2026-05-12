"""Authentication and user management endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    normalize_industries,
    normalize_role,
    public_user,
    require_super_admin,
)
from app.crud import get_system
from app.models import InventorySystem
from app.schemas import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    MessageResponse,
    UserCreateRequest,
    UserListResponse,
    UserMutationResponse,
    UserUpdateRequest,
)


router = APIRouter()


@router.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest, system: InventorySystem = Depends(get_system)) -> Dict[str, Any]:
    try:
        user = authenticate_user(system, request.username, request.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        return {
            "access_token": create_access_token(user),
            "token_type": "bearer",
            "user": user,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Authentication service unavailable: {exc}") from exc


@router.get("/auth/me", response_model=CurrentUserResponse)
async def me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        return {"user": public_user(user)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Authentication service unavailable: {exc}") from exc


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        users = [public_user(user) for user in system.database.list_users()]
        return {"users": users, "count": len(users)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"User service unavailable: {exc}") from exc


@router.post("/users", response_model=UserMutationResponse)
async def create_user(
    request: UserCreateRequest,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        role = normalize_role(request.role)
        industries = [] if role == "super_admin" else normalize_industries(request.industries)
        user = system.database.create_user(
            username=request.username,
            full_name=request.full_name,
            password=request.password,
            role=role,
            industries=industries,
            is_active=request.is_active,
        )
        return {"message": "User created.", "user": public_user(user)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to create user: {exc}") from exc


@router.patch("/users/{user_id}", response_model=UserMutationResponse)
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, Any]:
    try:
        updates = request.model_dump(exclude_unset=True)
        if "role" in updates and updates["role"] is not None:
            updates["role"] = normalize_role(updates["role"])
        role = updates.get("role")
        if "industries" in updates and updates["industries"] is not None:
            updates["industries"] = [] if role == "super_admin" else normalize_industries(updates["industries"])
        user = system.database.update_user(user_id, updates)
        return {"message": "User updated.", "user": public_user(user)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to update user: {exc}") from exc


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    _: Dict[str, Any] = Depends(require_super_admin),
    system: InventorySystem = Depends(get_system),
) -> Dict[str, str]:
    try:
        if not system.database.delete_user(user_id):
            raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' was not found.")
        return {"message": "User deleted."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete user: {exc}") from exc
