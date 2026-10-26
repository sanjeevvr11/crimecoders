"""FastAPI dependencies: who is signed in, what their role allows, and audit entries.

`require_role` is async on purpose: it sets the request's reveal flag (admins see
identifiers unmasked) in the request's own context, which the route then inherits.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app import config
from app.auth.store import ROLES, get_auth_store, rank
from app.masking import revealed, set_revealed

# with sign-in switched off the API keeps its old behaviour: every screen, identifiers masked
LOCAL_USER = {"id": 0, "username": "local", "display_name": None, "role": "admin", "active": True,
              "created_at": None, "last_login_at": None}


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def current_user(request: Request) -> dict:
    if not config.AUTH_ENABLED:
        set_revealed(False)
        return LOCAL_USER
    token = request.cookies.get(config.SESSION_COOKIE)
    user = get_auth_store().session_user(token) if token else None
    if user is None:
        raise HTTPException(401, "not signed in")
    set_revealed(user["role"] == "admin")
    return user


def require_role(role: str):
    assert role in ROLES

    async def check(user: dict = Depends(current_user)) -> dict:
        if rank(user["role"]) < rank(role):
            raise HTTPException(403, f"this needs the {role} role")
        return user

    return check


def audited(action: str, param: str | None = None):
    """Record `action` (with the path parameter `param` as its target) for the signed-in user."""

    async def log(request: Request, user: dict = Depends(current_user)) -> None:
        if not config.AUTH_ENABLED:
            return
        target = request.path_params.get(param) if param else None
        get_auth_store().log(action, user, target=target, unmasked=revealed(), ip=client_ip(request))

    return Depends(log)
