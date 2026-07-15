from __future__ import annotations

from app.core import security
from app.core.settings import AppSettings


def test_session_token_expires_at_exact_ttl(monkeypatch) -> None:
    settings = AppSettings.model_validate({"security": {"session_secret": "x" * 32}})
    monkeypatch.setattr(security.time, "time", lambda: 1_000)
    token = security.make_session_token(settings, "invite", "invite", 60)

    monkeypatch.setattr(security.time, "time", lambda: 1_060)
    assert security.verify_session_token(settings, token, "invite", "invite", 60)

    monkeypatch.setattr(security.time, "time", lambda: 1_061)
    assert not security.verify_session_token(settings, token, "invite", "invite", 60)
