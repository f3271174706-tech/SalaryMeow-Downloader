from __future__ import annotations

import time

from app.core.settings import AppSettings
from app.services.preload_service import PreloadedFile, PreloadService


def _settings(tmp_path) -> AppSettings:
    return AppSettings.model_validate(
        {
            "paths": {"downloads_dir": tmp_path},
            "resources": {
                "preload_enabled": True,
                "preload_platforms": ["douyin"],
                "preload_max_duration_seconds": 180,
                "preload_max_bytes": 100,
                "preload_cache_max_bytes": 200,
                "preload_cache_max_entries": 2,
                "preload_wait_seconds": 1,
            },
        }
    )


def test_preload_only_accepts_short_ordinary_videos(tmp_path) -> None:
    service = PreloadService(_settings(tmp_path))
    base = {
        "platform": "douyin",
        "type": "video",
        "duration": 5_000,
        "video_url": "https://www.douyin.com/video/1",
    }

    assert service._is_eligible(base)
    assert not service._is_eligible({**base, "duration": 181_000})
    assert not service._is_eligible({**base, "duration": 0})
    assert not service._is_eligible({**base, "type": "photo"})
    assert not service._is_eligible({**base, "platform": "tiktok"})


def test_preload_deduplicates_and_can_be_consumed(monkeypatch, tmp_path) -> None:
    service = PreloadService(_settings(tmp_path))
    output = tmp_path / "preloaded.mp4"
    calls = []

    def fake_download(info, quality):
        calls.append((info, quality))
        output.write_bytes(b"video")
        return PreloadedFile(output, "title.mp4", 5, time.monotonic())

    monkeypatch.setattr(service, "_download_media", fake_download)
    info = {
        "platform": "douyin",
        "type": "video",
        "duration": 5_000,
        "video_url": "https://www.douyin.com/video/1",
        "title": "title",
    }

    assert service.schedule("https://v.douyin.com/example/", info)
    assert not service.schedule("https://v.douyin.com/example/", info)
    assert service.consume("https://v.douyin.com/example/", "1080p") == (str(output), "title.mp4")
    assert len(calls) == 1
    assert service.consume("https://v.douyin.com/example/", "1080p") is None
