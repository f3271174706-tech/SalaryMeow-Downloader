from __future__ import annotations

import pytest

from app.legacy import douyin_api, downloader


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.douyin.com/video/7609268206426967338", "7609268206426967338"),
        ("https://www.douyin.com/note/7662302902605678073", "7662302902605678073"),
        ("https://www.iesdouyin.com/share/slides/7662302902605678073/", "7662302902605678073"),
        ("https://v.douyin.com/SwkAZTPHm4A/", None),
    ],
)
def test_extracts_aweme_id_from_known_url_shapes(url: str, expected: str | None) -> None:
    assert douyin_api._aweme_id_from_url(url) == expected


def _disable_cache(monkeypatch) -> None:
    monkeypatch.setattr(downloader, "_cache_get", lambda _url: None)
    monkeypatch.setattr(downloader, "_cache_set", lambda _url, _info: None)
    original_get = downloader.config.get
    monkeypatch.setattr(
        downloader.config,
        "get",
        lambda key, default=None: True if key == "api.enabled" else 5 if key == "api.timeout" else original_get(key, default),
    )


def test_douyin_uses_only_f2_api(monkeypatch) -> None:
    _disable_cache(monkeypatch)

    async def fake_api(_url: str, cookie: str | None = None) -> dict:
        return {"title": "api", "type": "video", "platform": "douyin", "video_url": "https://example.test/v"}

    monkeypatch.setattr(douyin_api, "_extract_douyin_api", fake_api)
    monkeypatch.setattr(downloader, "_extract_douyin", lambda _url: pytest.fail("crawler must not run"))

    result = downloader.extract_video_info("https://v.douyin.com/api-only-success/")

    assert result["title"] == "api"


def test_douyin_api_empty_result_does_not_fall_back(monkeypatch) -> None:
    _disable_cache(monkeypatch)
    calls = []

    async def fake_api(_url: str, cookie: str | None = None) -> None:
        calls.append(cookie)
        return None

    monkeypatch.setattr(douyin_api, "_extract_douyin_api", fake_api)
    monkeypatch.setattr(downloader, "_extract_douyin", lambda _url: pytest.fail("crawler must not run"))

    with pytest.raises(RuntimeError, match="两次均返回空数据"):
        downloader.extract_video_info("https://v.douyin.com/api-only-empty/")

    assert len(calls) == 2


def test_douyin_switches_cookie_once_then_succeeds(monkeypatch) -> None:
    _disable_cache(monkeypatch)
    calls = []
    monkeypatch.setattr(downloader.config, "get_cookie", lambda _platform: "cookie-a")
    monkeypatch.setattr(
        downloader.config,
        "rotate_cookie",
        lambda _platform, failed_cookie="": "cookie-b" if failed_cookie == "cookie-a" else pytest.fail("bad cookie"),
    )

    async def fake_api(_url: str, cookie: str | None = None) -> dict | None:
        calls.append(cookie)
        if cookie == "cookie-b":
            return {"title": "retry", "type": "video", "platform": "douyin", "video_url": "https://example.test/v"}
        return None

    monkeypatch.setattr(douyin_api, "_extract_douyin_api", fake_api)
    monkeypatch.setattr(downloader, "_extract_douyin", lambda _url: pytest.fail("crawler must not run"))

    result = downloader.extract_video_info("https://v.douyin.com/api-only-cookie-retry/")

    assert result["title"] == "retry"
    assert calls == ["cookie-a", "cookie-b"]
