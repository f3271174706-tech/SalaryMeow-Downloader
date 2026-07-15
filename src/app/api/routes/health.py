"""Health check routes."""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.dependencies import settings_dep
from app.core.settings import AppSettings

router = APIRouter(prefix="/health", tags=["health"])


def _playwright_status() -> str:
    if importlib.util.find_spec("playwright") is None:
        return "missing"
    candidates = [
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("msedge"),
        "/snap/bin/chromium",
        str(Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe"),
        str(Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe"),
    ]
    browser_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if browser_path and Path(browser_path).exists() and any(Path(browser_path).glob("chromium-*")):
        return "ok"
    return "ok" if any(candidate and Path(candidate).is_file() for candidate in candidates) else "package-only"


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(settings: AppSettings = Depends(settings_dep)) -> dict:
    checks = {
        "config": "ok",
        "data_dir": "ok" if settings.paths.data_dir.exists() else "missing",
        "downloads_dir": "ok" if settings.paths.downloads_dir.exists() else "missing",
        "logs_dir": "ok" if settings.paths.logs_dir.exists() else "missing",
        "ffmpeg": "ok" if shutil.which("ffmpeg") else "degraded",
        "playwright": _playwright_status(),
        "admin": "enabled" if settings.admin_enabled else "disabled",
        "proxy_headers": "trusted" if settings.security.trust_proxy_headers else "ignored",
    }
    status = (
        "ok"
        if all(
            value in {"ok", "enabled", "disabled", "ignored", "trusted", "degraded", "package-only"}
            for value in checks.values()
        )
        else "error"
    )
    return {"status": status, "checks": checks}
