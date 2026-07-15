"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, auth, download, health, pages, parse, stream
from app.core.middleware import SecurityHeadersMiddleware
from app.core.settings import get_settings
from app.lifespan import lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.title, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Range"],
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.mount("/static", StaticFiles(directory=settings.paths.web_static_dir), name="static")
    for router in (
        health.router,
        auth.router,
        admin.router,
        parse.router,
        stream.router,
        download.router,
        pages.router,
    ):
        application.include_router(router)
    return application


app = create_app()
