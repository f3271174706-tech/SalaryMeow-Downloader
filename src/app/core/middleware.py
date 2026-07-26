"""HTTP middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

from .security import SECURITY_HEADERS


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/admin-assets/"):
            response.headers.setdefault(
                "Cache-Control",
                "public, max-age=2592000, stale-while-revalidate=86400",
            )
        elif request.url.path in {"/admin", "/admin/login"}:
            response.headers.setdefault("Cache-Control", "no-cache")
        return response
