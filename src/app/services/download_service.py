"""Media download service."""

from __future__ import annotations

from pathlib import Path

from app.core.settings import AppSettings
from app.infrastructure.storage import ensure_within_directory, has_min_free_space
from app.infrastructure.url_safety import validate_url
from app.legacy.downloader import download_video


class DownloadTooLargeError(RuntimeError):
    pass


class InsufficientStorageError(RuntimeError):
    pass


class DownloadService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def download(
        self,
        *,
        url: str,
        quality: str,
        media_type: str,
        image_index: int,
        live_photo_format: bool,
        live_photo_index: int,
    ) -> tuple[str, str]:
        safe = validate_url(url)
        minimum_free = min(self.settings.resources.max_download_bytes, 64 * 1024 * 1024)
        if not has_min_free_space(self.settings.paths.downloads_dir, minimum_free):
            raise InsufficientStorageError("Insufficient free disk space")
        file_path, filename = download_video(
            safe.normalized,
            quality=quality,
            media_type=media_type,
            image_index=image_index,
            live_photo_format=live_photo_format,
            live_photo_index=live_photo_index,
        )
        resolved = ensure_within_directory(Path(file_path), self.settings.paths.downloads_dir)
        if not resolved.is_file():
            raise FileNotFoundError("Downloader did not produce a regular file")
        if resolved.stat().st_size > self.settings.resources.max_download_bytes:
            resolved.unlink(missing_ok=True)
            raise DownloadTooLargeError("Downloaded media exceeds the configured size limit")
        return str(resolved), filename
