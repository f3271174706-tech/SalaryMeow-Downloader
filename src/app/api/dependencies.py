"""FastAPI dependency wiring."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from app.core.security import get_client_ip
from app.core.settings import AppSettings, get_settings
from app.infrastructure.rate_limit import AsyncConcurrencyLimit, ConcurrencyLimit, RateLimiter
from app.services.auth_service import AuthService
from app.services.download_service import DownloadService
from app.services.parser_service import ParserService
from app.services.record_service import RecordService
from app.services.stream_service import StreamService


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(get_settings())


@lru_cache(maxsize=1)
def get_record_service() -> RecordService:
    return RecordService(get_settings())


@lru_cache(maxsize=1)
def get_parser_service() -> ParserService:
    return ParserService()


@lru_cache(maxsize=1)
def get_download_service() -> DownloadService:
    return DownloadService(get_settings())


@lru_cache(maxsize=1)
def get_stream_service() -> StreamService:
    return StreamService(get_settings())


@lru_cache(maxsize=1)
def parse_limit() -> ConcurrencyLimit:
    return ConcurrencyLimit(get_settings().resources.parse_concurrency)


@lru_cache(maxsize=1)
def download_limit() -> ConcurrencyLimit:
    return ConcurrencyLimit(get_settings().resources.download_concurrency)


@lru_cache(maxsize=1)
def stream_limit() -> AsyncConcurrencyLimit:
    return AsyncConcurrencyLimit(get_settings().resources.stream_concurrency)


@lru_cache(maxsize=1)
def api_rate_limiter() -> RateLimiter:
    return RateLimiter(limit=60, window_seconds=60)


def require_invite_session(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(api_rate_limiter),
    settings: AppSettings = Depends(get_settings),
) -> None:
    client = get_client_ip(request, settings) or "unknown"
    if not limiter.allow(client):
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail="请求过于频繁")
    auth.require_invite_session(request)


def require_admin_session(request: Request, auth: AuthService = Depends(get_auth_service)) -> None:
    auth.require_admin_session(request)


def settings_dep() -> AppSettings:
    return get_settings()
