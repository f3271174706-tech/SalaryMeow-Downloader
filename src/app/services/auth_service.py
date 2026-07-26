"""Authentication service for invite and admin sessions."""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response, status

from app.core.security import (
    ADMIN_COOKIE_NAME,
    AdminSession,
    get_client_ip,
    is_trusted_admin_origin,
    make_admin_session_token,
    make_session_token,
    verify_admin_password,
    verify_admin_session_token,
    verify_invite_code,
    verify_session_token,
)
from app.core.settings import AppSettings


class AuthService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._admin_failures: dict[str, list[float]] = defaultdict(list)
        self._invite_failures: dict[str, list[float]] = defaultdict(list)
        self._failure_lock = threading.Lock()

    def require_invite_session(self, request: Request) -> None:
        if not self.settings.security.invite_auth_enabled:
            return
        token = request.cookies.get("direct_invite", "")
        if not verify_session_token(
            self.settings,
            token,
            "invite",
            "invite",
            self.settings.security.invite_session_ttl_seconds,
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要邀请码会话")

    def verify_invite(self, code: str, request: Request, response: Response) -> dict[str, bool]:
        if not self.settings.security.invite_auth_enabled:
            return {"success": True}
        ip = get_client_ip(request, self.settings)
        self._check_failures(self._invite_failures, ip)
        if not verify_invite_code(self.settings, code.strip()):
            with self._failure_lock:
                self._invite_failures[ip].append(time.time())
            raise HTTPException(status_code=401, detail="邀请码错误")
        with self._failure_lock:
            self._invite_failures.pop(ip, None)
        token = make_session_token(
            self.settings,
            "invite",
            "invite",
            self.settings.security.invite_session_ttl_seconds,
        )
        response.set_cookie(
            "direct_invite",
            token,
            max_age=self.settings.security.invite_session_ttl_seconds,
            httponly=True,
            secure=self.settings.security.secure_cookies,
            samesite="lax",
        )
        return {"success": True}

    def current_admin_session(self, request: Request) -> AdminSession | None:
        return verify_admin_session_token(self.settings, request.cookies.get(ADMIN_COOKIE_NAME, ""))

    def require_admin_session(self, request: Request) -> AdminSession:
        if not self.settings.admin_enabled:
            raise HTTPException(status_code=503, detail="Admin login is not configured")
        session = self.current_admin_session(request)
        if session is None:
            raise HTTPException(status_code=401, detail="未登录")
        return session

    def login_admin(self, username: str, password: str, request: Request, response: Response) -> dict[str, str | int]:
        if not self.settings.admin_enabled:
            raise HTTPException(status_code=503, detail="Admin login is not configured")
        if not is_trusted_admin_origin(request, self.settings):
            raise HTTPException(status_code=403, detail="Untrusted request origin")
        ip = get_client_ip(request, self.settings)
        self._check_failures(self._admin_failures, ip)
        user_matches = hmac.compare_digest(username.encode(), self.settings.security.admin_user.encode())
        if self.settings.security.admin_password_hash:
            password_matches = verify_admin_password(password, self.settings.security.admin_password_hash)
        else:
            password_matches = hmac.compare_digest(password.encode(), self.settings.security.admin_password.encode())
        if not (user_matches and password_matches):
            with self._failure_lock:
                self._admin_failures[ip].append(time.time())
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        with self._failure_lock:
            self._admin_failures.pop(ip, None)
        token = make_admin_session_token(self.settings, self.settings.security.admin_user)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            max_age=self.settings.security.admin_session_ttl_seconds,
            httponly=True,
            secure=self.settings.security.secure_cookies,
            samesite="strict",
            path="/",
        )
        session = verify_admin_session_token(self.settings, token)
        if session is None:  # pragma: no cover
            raise RuntimeError("Generated admin session could not be verified")
        return {"username": session.username, "expiresAt": session.expires_at}

    def admin_session_status(self, request: Request) -> dict[str, str | int]:
        session = self.require_admin_session(request)
        return {
            "username": session.username,
            "issuedAt": session.issued_at,
            "expiresAt": session.expires_at,
        }

    def logout_admin(self, request: Request, response: Response) -> None:
        if not is_trusted_admin_origin(request, self.settings):
            raise HTTPException(status_code=403, detail="Untrusted request origin")
        response.delete_cookie(
            ADMIN_COOKIE_NAME,
            path="/",
            secure=self.settings.security.secure_cookies,
            httponly=True,
            samesite="strict",
        )

    def _check_failures(self, storage: dict[str, list[float]], key: str) -> None:
        now = time.time()
        with self._failure_lock:
            limit = self.settings.security.admin_max_login_failures if storage is self._admin_failures else 5
            window = (
                self.settings.security.admin_login_failure_window_seconds if storage is self._admin_failures else 900
            )
            recent = [item for item in storage.get(key, []) if now - item < window]
            if recent:
                storage[key] = recent
            else:
                storage.pop(key, None)
            if len(recent) >= limit:
                raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")
