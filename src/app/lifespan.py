"""Application lifespan management."""

from __future__ import annotations

import asyncio
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.legacy.downloader import cleanup_old_files

logger = logging.getLogger(__name__)


def prewarm_f2() -> None:
    """Load the f2 Douyin request stack before the first user request."""
    importlib.import_module("f2.apps.douyin.crawler")
    importlib.import_module("f2.apps.douyin.model")
    importlib.import_module("f2.apps.douyin.utils")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    cleanup_old_files(max_age_seconds=1800)
    if settings.resources.f2_prewarm_enabled:
        try:
            await asyncio.to_thread(prewarm_f2)
            logger.info("f2 Douyin stack prewarmed")
        except Exception:
            # A warmup failure must not make the whole API unavailable; the
            # normal request path can still retry/import f2 and report errors.
            logger.warning("f2 prewarm failed; continuing startup", exc_info=True)
    yield
