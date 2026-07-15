from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client(monkeypatch, *, invite_auth_enabled: bool = True):
    monkeypatch.setenv("DOUYIN_SESSION_SECRET", "test-session-secret-test-session-secret")
    monkeypatch.setenv("DOUYIN_INVITE_CODES", "let-me-in")
    monkeypatch.setenv("DOUYIN_INVITE_AUTH_ENABLED", str(invite_auth_enabled).lower())
    monkeypatch.delenv("ADMIN_PASS", raising=False)
    monkeypatch.setenv("DOUYIN_SECURE_COOKIES", "false")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    from app.api import dependencies

    dependencies.get_auth_service.cache_clear()
    module = importlib.import_module("app.main")
    return TestClient(module.create_app())


def test_parse_requires_invite_session(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/api/parse", json={"url": "https://www.douyin.com/video/123"})

    assert response.status_code == 401


def test_invite_sets_httponly_cookie(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post("/api/verify-invite", json={"code": "let-me-in"})

    assert response.status_code == 200
    assert "direct_invite=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_invite_cookie_works_over_documented_local_http(monkeypatch) -> None:
    client = _client(monkeypatch)

    login = client.post("/api/verify-invite", json={"code": "let-me-in"})
    index = client.get("/")

    assert login.status_code == 200
    assert index.status_code == 200
    assert "Secure" not in login.headers["set-cookie"]


def test_admin_records_default_denied_when_admin_disabled(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/api/admin/records")

    assert response.status_code == 503


def test_invite_auth_can_be_disabled(monkeypatch) -> None:
    client = _client(monkeypatch, invite_auth_enabled=False)

    index = client.get("/")
    verification = client.post("/api/verify-invite", json={"code": "anything"})

    assert index.status_code == 200
    assert verification.status_code == 200
    assert "direct_invite=" not in verification.headers.get("set-cookie", "")
