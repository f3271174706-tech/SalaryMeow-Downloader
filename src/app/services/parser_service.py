"""Video parsing service."""

from __future__ import annotations

from app.infrastructure.url_safety import validate_url
from app.legacy.downloader import extract_video_info


class ParserService:
    def parse(self, url: str) -> dict:
        safe = validate_url(url)
        return extract_video_info(safe.normalized)
