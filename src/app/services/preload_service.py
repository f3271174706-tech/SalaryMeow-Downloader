"""Bounded background preloading for small, ordinary videos."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.settings import AppSettings
from app.infrastructure.storage import has_min_free_space
from app.infrastructure.url_safety import normalize_input_url, validate_url
from app.legacy.downloader import MOBILE_UA, apply_quality

logger = logging.getLogger(__name__)


@dataclass
class PreloadedFile:
    path: Path
    filename: str
    size: int
    created_at: float


class PreloadService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._entries: dict[str, PreloadedFile] = {}
        self._pending: dict[str, Future[None]] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.resources.preload_concurrency),
            thread_name_prefix="media-preload",
        )

    @staticmethod
    def _key(url: str, quality: str) -> str:
        return f"{normalize_input_url(url)}|{quality.lower()}"

    @staticmethod
    def _duration_seconds(platform: str, raw_duration: Any) -> float:
        try:
            duration = max(0.0, float(raw_duration or 0))
        except (TypeError, ValueError):
            return 0.0
        if platform in {"douyin", "tiktok"} and duration > 1000:
            return duration / 1000
        return duration

    def _is_eligible(self, info: dict) -> bool:
        resources = self.settings.resources
        platform = str(info.get("platform", ""))
        duration = self._duration_seconds(platform, info.get("duration"))
        return bool(
            resources.preload_enabled
            and info.get("type") == "video"
            and info.get("video_url")
            and platform in resources.preload_platforms
            and 0 < duration <= resources.preload_max_duration_seconds
        )

    def schedule(self, source_url: str, info: dict, quality: str = "1080p") -> bool:
        if not self._is_eligible(info):
            return False
        key = self._key(source_url, quality)
        with self._lock:
            self._cleanup_locked()
            if key in self._entries or key in self._pending:
                return False
            future = self._executor.submit(self._run, key, info.copy(), quality)
            self._pending[key] = future

            def clear_pending(completed: Future[None]) -> None:
                self._clear_pending(key, completed)

            future.add_done_callback(clear_pending)
        return True

    def consume(self, source_url: str, quality: str) -> tuple[str, str] | None:
        key = self._key(source_url, quality)
        with self._lock:
            self._cleanup_locked()
            pending = self._pending.get(key)
        if pending is not None:
            with suppress(Exception):
                pending.result(timeout=max(0.0, self.settings.resources.preload_wait_seconds))
        with self._lock:
            self._cleanup_locked()
            entry = self._entries.pop(key, None)
        if entry is None or not entry.path.is_file():
            return None
        logger.info("Smart preload cache hit: %s (%d bytes)", entry.filename, entry.size)
        return str(entry.path), entry.filename

    def cleanup_expired(self) -> int:
        with self._lock:
            return self._cleanup_locked()

    def _cleanup_locked(self) -> int:
        now = time.monotonic()
        ttl = self.settings.resources.metadata_cache_ttl_seconds
        expired = [
            key for key, entry in self._entries.items() if now - entry.created_at >= ttl or not entry.path.is_file()
        ]
        for key in expired:
            entry = self._entries.pop(key)
            entry.path.unlink(missing_ok=True)
        return len(expired)

    def _run(self, key: str, info: dict, quality: str) -> None:
        try:
            entry = self._download_media(info, quality)
            with self._lock:
                self._add_entry_locked(key, entry)
            logger.info("Smart preload completed: %s (%d bytes)", entry.filename, entry.size)
        except Exception:
            logger.info("Smart preload skipped or failed", exc_info=True)

    def _clear_pending(self, key: str, future: Future[None]) -> None:
        with self._lock:
            if self._pending.get(key) is future:
                self._pending.pop(key, None)

    def _add_entry_locked(self, key: str, entry: PreloadedFile) -> None:
        resources = self.settings.resources
        self._cleanup_locked()
        while self._entries and (
            len(self._entries) >= resources.preload_cache_max_entries
            or sum(item.size for item in self._entries.values()) + entry.size > resources.preload_cache_max_bytes
        ):
            oldest_key = min(self._entries, key=lambda item: self._entries[item].created_at)
            oldest = self._entries.pop(oldest_key)
            oldest.path.unlink(missing_ok=True)
        if entry.size <= resources.preload_cache_max_bytes:
            self._entries[key] = entry
        else:
            entry.path.unlink(missing_ok=True)

    @staticmethod
    def _headers_for(platform: str) -> dict[str, str]:
        headers = {"User-Agent": MOBILE_UA}
        referers = {
            "douyin": "https://www.douyin.com/",
            "bilibili": "https://www.bilibili.com/",
            "kuaishou": "https://www.kuaishou.com/",
            "tiktok": "https://www.tiktok.com/",
            "twitter": "https://x.com/",
        }
        if platform in referers:
            headers["Referer"] = referers[platform]
        return headers

    def _download_media(self, info: dict, quality: str) -> PreloadedFile:
        resources = self.settings.resources
        candidate = validate_url(str(info["video_url"]), resolve_dns=False)
        platform = str(info.get("platform", candidate.platform))
        if candidate.platform != platform:
            raise ValueError("Media URL platform mismatch")
        proxy = self.settings.network.proxy if platform in {"tiktok", "twitter"} else None
        safe = validate_url(candidate.normalized, platform=platform, resolve_dns=proxy is None)
        target = apply_quality(safe.normalized, quality) if platform == "douyin" else safe.normalized
        minimum_free = min(resources.preload_max_bytes, 64 * 1024 * 1024)
        if not has_min_free_space(self.settings.paths.downloads_dir, minimum_free):
            raise OSError("Insufficient storage for preload")

        timeout = httpx.Timeout(
            connect=resources.request_timeout_seconds,
            read=resources.stream_read_timeout_seconds,
            write=10,
            pool=10,
        )
        client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, proxy=proxy)
        response: httpx.Response | None = None
        part_path = self.settings.paths.downloads_dir / f".preload-{uuid.uuid4().hex}.part"
        final_path = part_path.with_suffix(".mp4")
        try:
            current_url = target
            for _ in range(resources.max_redirects + 1):
                response = client.send(
                    client.build_request("GET", current_url, headers=self._headers_for(platform)), stream=True
                )
                if not response.is_redirect:
                    break
                location = response.headers.get("location", "")
                response.close()
                response = None
                if not location:
                    raise httpx.HTTPError("Redirect response is missing Location")
                current_url = validate_url(
                    str(httpx.URL(current_url).join(location)),
                    platform=platform,
                    resolve_dns=proxy is None,
                ).normalized
            else:
                raise httpx.TooManyRedirects("Too many redirects")
            response.raise_for_status()
            declared = int(response.headers.get("content-length", "0") or 0)
            if declared > resources.preload_max_bytes:
                raise ValueError("Media is too large for smart preload")
            total = 0
            with part_path.open("wb") as output:
                for chunk in response.iter_bytes(65536):
                    total += len(chunk)
                    if total > resources.preload_max_bytes:
                        raise ValueError("Media exceeded smart preload limit")
                    output.write(chunk)
            os.replace(part_path, final_path)
            safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", str(info.get("title", "")))[:80].strip()
            filename = f"{safe_title or 'video'}.mp4"
            return PreloadedFile(final_path, filename, total, time.monotonic())
        finally:
            if response is not None:
                response.close()
            client.close()
            part_path.unlink(missing_ok=True)
