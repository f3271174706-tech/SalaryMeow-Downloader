"""Invite and admin authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.api.dependencies import get_auth_service
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


class InviteRequest(BaseModel):
    code: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


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
) -> dict[str, bool]:
    return auth.login_admin(payload.username, payload.password, request, response)


@router.post("/api/admin/logout")
def admin_logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("admin_session")
    return {"success": True}
