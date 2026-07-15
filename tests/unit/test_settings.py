from __future__ import annotations

import pytest

from app.core.settings import AppSettings


def test_production_requires_stable_session_secret() -> None:
    settings = AppSettings.model_validate({"security": {"app_env": "production", "invite_codes": ["x"]}})

    with pytest.raises(RuntimeError):
        settings.validate_for_startup()


def test_production_requires_secure_cookies() -> None:
    settings = AppSettings.model_validate(
        {
            "security": {
                "app_env": "production",
                "session_secret": "x" * 32,
                "invite_codes": ["x"],
                "secure_cookies": False,
            }
        }
    )

    with pytest.raises(RuntimeError, match="DOUYIN_SECURE_COOKIES"):
        settings.validate_for_startup()


def test_repr_secret_redaction_from_legacy_config() -> None:
    from app.legacy.config import config

    assert "Cookie" not in repr(config) or "***" in repr(config)


def test_network_proxy_is_loaded() -> None:
    settings = AppSettings.model_validate({"network": {"proxy": "http://127.0.0.1:7897"}})

    assert settings.network.proxy == "http://127.0.0.1:7897"
