from __future__ import annotations

import pytest

from app.core.settings import AppSettings
from app.services import download_service
from app.services.download_service import DownloadService, DownloadTooLargeError


def _settings(tmp_path, max_bytes: int = 10) -> AppSettings:
    return AppSettings.model_validate(
        {
            "paths": {"downloads_dir": tmp_path},
            "resources": {"max_download_bytes": max_bytes},
        }
    )


def test_download_rejects_path_outside_download_directory(monkeypatch, tmp_path) -> None:
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"x")
    monkeypatch.setattr(download_service, "validate_url", lambda url: type("Safe", (), {"normalized": url})())
    monkeypatch.setattr(download_service, "download_video", lambda *args, **kwargs: (str(outside), "outside.mp4"))

    with pytest.raises(ValueError, match="escapes"):
        DownloadService(_settings(tmp_path)).download(
            url="https://www.douyin.com/video/1",
            quality="1080p",
            media_type="video",
            image_index=0,
            live_photo_format=False,
            live_photo_index=0,
        )


def test_download_removes_file_over_limit(monkeypatch, tmp_path) -> None:
    output = tmp_path / "large.mp4"
    output.write_bytes(b"x" * 11)
    monkeypatch.setattr(download_service, "validate_url", lambda url: type("Safe", (), {"normalized": url})())
    monkeypatch.setattr(download_service, "download_video", lambda *args, **kwargs: (str(output), "large.mp4"))

    with pytest.raises(DownloadTooLargeError):
        DownloadService(_settings(tmp_path)).download(
            url="https://www.douyin.com/video/1",
            quality="1080p",
            media_type="video",
            image_index=0,
            live_photo_format=False,
            live_photo_index=0,
        )

    assert not output.exists()
