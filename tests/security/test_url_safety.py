from __future__ import annotations

import pytest

from app.infrastructure import url_safety
from app.infrastructure.url_safety import UrlSafetyError, validate_url


def test_allows_exact_and_subdomain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "_resolve_host", lambda hostname: {"8.8.8.8"})

    assert validate_url("https://www.douyin.com/video/123").platform == "douyin"
    assert validate_url("https://video.twimg.com/ext_tw_video/1").platform == "twitter"


def test_allows_kuaishou_official_redirect_and_cdn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "_resolve_host", lambda hostname: {"8.8.8.8"})

    assert validate_url("https://m.gifshow.com/fw/photo/abc123").platform == "kuaishou"
    assert validate_url("https://hwmov.a.yximgs.com/upic/example.mp4").platform == "kuaishou"


def test_allows_bilibili_specific_akamai_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "_resolve_host", lambda hostname: {"8.8.8.8"})

    assert validate_url("https://upos-hz-mirrorakam.akamaized.net/video.m4s").platform == "bilibili"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://douyin.com.evil.example/video/1",
        "https://evil.example/?next=https://douyin.com/video/1",
        "https://user:pass@douyin.com/video/1",
        "https://127.0.0.1/video",
        "https://[::1]/video",
        "https://169.254.169.254/latest/meta-data",
        "https://localhost/video",
    ],
)
def test_rejects_ssrf_and_confused_hosts(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setattr(
        url_safety, "_resolve_host", lambda hostname: {"127.0.0.1"} if hostname == "localhost" else {"8.8.8.8"}
    )

    with pytest.raises(UrlSafetyError):
        validate_url(url)


def test_rejects_allowed_domain_that_resolves_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "_resolve_host", lambda hostname: {"10.0.0.8"})

    with pytest.raises(UrlSafetyError):
        validate_url("https://www.douyin.com/video/123")


def test_platform_must_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_safety, "_resolve_host", lambda hostname: {"8.8.8.8"})

    with pytest.raises(UrlSafetyError):
        validate_url("https://www.douyin.com/video/123", platform="twitter")
