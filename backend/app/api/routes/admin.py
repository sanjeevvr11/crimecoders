"""Admin only: manage who can sign in, and read the audit log."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth.deps import client_ip, require_role
from app.auth.store import AuthError, get_auth_store
from app.schemas.api import AuditPage, User, UserCreate, UserUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[User])
def users() -> list[dict]:
    return get_auth_store().users()


@router.post("/users", response_model=User)
def create_user(body: UserCreate, request: Request, admin: dict = Depends(require_role("admin"))) -> dict:
    store = get_auth_store()
    try:
        user = store.create_user(body.username, body.password, body.role, body.display_name)
    except AuthError as e:
        raise HTTPException(400, str(e)) from None
    store.log("user_create", admin, target=user["username"], ip=client_ip(request), detail=f"role {user['role']}")
    return user


@router.patch("/users/{user_id}", response_model=User)
def update_user(user_id: int, body: UserUpdate, request: Request, admin: dict = Depends(require_role("admin"))) -> dict:
    store = get_auth_store()
    try:
        user = store.update_user(user_id, role=body.role, active=body.active, password=body.password, display_name=body.display_name)
    except KeyError:
        raise HTTPException(404, f"unknown user {user_id}") from None
    except AuthError as e:
        raise HTTPException(400, str(e)) from None
    changes = [f"role {body.role}" if body.role else "", "" if body.active is None else ("reactivated" if body.active else "deactivated"),
               "password reset" if body.password else "", "name changed" if body.display_name is not None else ""]
    store.log("user_update", admin, target=user["username"], ip=client_ip(request), detail=", ".join(c for c in changes if c) or None)
    return user


@router.get("/audit", response_model=AuditPage)
def audit(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
          username: str | None = None, action: str | None = None) -> dict:
    return get_auth_store().audit(limit, offset, username, action)
