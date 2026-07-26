"""Invite and admin authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.api.dependencies import get_auth_service
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


class InviteRequest(BaseModel):
    code: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


@router.get("/api/public/config")
def public_config(auth: AuthService = Depends(get_auth_service)) -> dict[str, str | bool]:
    settings = auth.settings
    return {
        "appName": settings.security.admin_app_name,
        "appDescription": settings.security.admin_app_description,
        "adminEnabled": settings.admin_enabled,
    }


@router.post("/api/verify-invite")
def verify_invite(
    payload: InviteRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> dict[str, bool]:
    return auth.verify_invite(payload.code, request, response)


@router.post("/api/admin/login")
def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> dict[str, str | int]:
    return auth.login_admin(payload.username, payload.password, request, response)


@router.get("/api/admin/session")
def admin_session(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
) -> dict[str, str | int]:
    return auth.admin_session_status(request)


@router.post("/api/admin/logout", status_code=status.HTTP_204_NO_CONTENT)
def admin_logout(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    auth.logout_admin(request, response)
