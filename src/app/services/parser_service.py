"""Video parsing service."""

from __future__ import annotations

import logging

from app.core.settings import AppSettings
from app.infrastructure.metadata_cache import MetadataCache
from app.infrastructure.url_safety import validate_url
from app.legacy.downloader import extract_video_info

logger = logging.getLogger(__name__)


class ParserService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.cache = MetadataCache(
            ttl_seconds=settings.resources.metadata_cache_ttl_seconds,
            max_entries=settings.resources.metadata_cache_max_entries,
        )

    def _resolve_dns_for(self, platform: str) -> bool:
        return not (self.settings.network.proxy and platform in {"tiktok", "twitter"})

    def parse(self, url: str) -> dict:
        candidate = validate_url(url, resolve_dns=False)
        safe = validate_url(
            candidate.normalized,
            resolve_dns=self._resolve_dns_for(candidate.platform),
        )
        cached = self.cache.get(safe.normalized)
        if cached is not None:
            logger.info("Metadata cache hit: platform=%s", safe.platform)
            return cached
        result = extract_video_info(safe.normalized)
        self.cache.set(safe.normalized, result)
        return result
