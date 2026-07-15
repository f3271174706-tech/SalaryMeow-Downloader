from __future__ import annotations

import httpx
import pytest

from app.infrastructure import safe_http, url_safety
from app.infrastructure.url_safety import UrlSafetyError


def test_redirect_is_revalidated_before_second_request(monkeypatch) -> None:
    monkeypatch.setattr(url_safety, "_resolve_host", lambda hostname: {"8.8.8.8"})
    calls: list[str] = []

    def fake_get(url: str, **kwargs) -> httpx.Response:
        calls.append(url)
        request = httpx.Request("GET", url)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"}, request=request)

    monkeypatch.setattr(safe_http.httpx, "get", fake_get)

    with pytest.raises(UrlSafetyError):
        safe_http.safe_get("https://www.douyin.com/video/1")

    assert len(calls) == 1
