"""Authentication service for invite and admin sessions."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response, status

from app.core.security import get_client_ip, make_session_token, verify_invite_code, verify_session_token
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

    def require_admin_session(self, request: Request) -> None:
        if not self.settings.admin_enabled:
            raise HTTPException(status_code=503, detail="Admin module is disabled until ADMIN_PASS is configured")
        token = request.cookies.get("admin_session", "")
        if not verify_session_token(
            self.settings,
            token,
            self.settings.security.admin_user,
            "admin",
            self.settings.security.admin_session_ttl_seconds,
        ):
            raise HTTPException(status_code=401, detail="未登录")

    def login_admin(self, username: str, password: str, request: Request, response: Response) -> dict[str, bool]:
        if not self.settings.admin_enabled:
            raise HTTPException(status_code=503, detail="Admin module is disabled until ADMIN_PASS is configured")
        ip = get_client_ip(request, self.settings)
        self._check_failures(self._admin_failures, ip)
        if username != self.settings.security.admin_user or password != self.settings.security.admin_password:
            with self._failure_lock:
                self._admin_failures[ip].append(time.time())
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        with self._failure_lock:
            self._admin_failures.pop(ip, None)
        token = make_session_token(
            self.settings,
            self.settings.security.admin_user,
            "admin",
            self.settings.security.admin_session_ttl_seconds,
        )
        response.set_cookie(
            "admin_session",
            token,
            max_age=self.settings.security.admin_session_ttl_seconds,
            httponly=True,
            secure=self.settings.security.secure_cookies,
            samesite="lax",
        )
        return {"success": True}

    def _check_failures(self, storage: dict[str, list[float]], key: str) -> None:
        now = time.time()
        with self._failure_lock:
            recent = [item for item in storage[key] if now - item < 900]
            if recent:
                storage[key] = recent
            else:
                storage.pop(key, None)
            if len(recent) >= 5:
                raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")
