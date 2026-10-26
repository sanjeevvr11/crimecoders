"""Sign in and out. The session lives in an httpOnly cookie, never in JavaScript."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app import config
from app.auth.deps import client_ip, current_user
from app.auth.store import get_auth_store
from app.masking import revealed, set_revealed
from app.schemas.api import LoginRequest, Me, SignedOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

_failures: dict[tuple, deque] = defaultdict(deque)  # (ip, username) -> failure times


def _too_many(key: tuple) -> bool:
    window = config.LOGIN_WINDOW_MINUTES * 60
    q = _failures[key]
    while q and q[0] < time.monotonic() - window:
        q.popleft()
    return len(q) >= config.LOGIN_MAX_FAILURES


def _me(user: dict) -> dict:
    return {"user": user, "auth_enabled": config.AUTH_ENABLED, "unmasked": revealed()}


@router.post("/login", response_model=Me)
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    if not config.AUTH_ENABLED:
        raise HTTPException(409, "sign-in is switched off (TRACE360_AUTH=off)")
    store, ip = get_auth_store(), client_ip(request)
    key = (ip, body.username.strip().lower())
    if _too_many(key):
        raise HTTPException(429, f"too many failed attempts; try again in {config.LOGIN_WINDOW_MINUTES} minutes")
    user = store.check_login(body.username, body.password)
    if user is None:
        _failures[key].append(time.monotonic())
        store.log("login_failed", username=body.username.strip()[:40], ip=ip)
        raise HTTPException(401, "wrong user name or password")
    _failures.pop(key, None)
    token = store.new_session(user["id"])
    response.set_cookie(config.SESSION_COOKIE, token, max_age=config.SESSION_HOURS * 3600, httponly=True,
                        samesite="lax", secure=config.COOKIE_SECURE, path="/")
    store.log("login", user, ip=ip)
    set_revealed(user["role"] == "admin")
    return _me(user)


@router.post("/logout", response_model=SignedOut)
async def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(config.SESSION_COOKIE)
    if token and config.AUTH_ENABLED:
        store = get_auth_store()
        user = store.session_user(token)
        store.end_session(token)
        if user:
            store.log("logout", user, ip=client_ip(request))
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"status": "signed out"}


@router.get("/me", response_model=Me)
async def me(user: dict = Depends(current_user)) -> dict:
    return _me(user)
