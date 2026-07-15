from app.core.settings import AppSettings
from app.services.parser_service import ParserService
from app.services.stream_service import StreamService


def test_proxy_is_limited_to_tiktok_and_twitter() -> None:
    settings = AppSettings.model_validate({"network": {"proxy": "http://127.0.0.1:7897"}})
    service = StreamService(settings)

    assert service._proxy_for_platform("tiktok") == "http://127.0.0.1:7897"
    assert service._proxy_for_platform("twitter") == "http://127.0.0.1:7897"
    assert service._proxy_for_platform("douyin") is None
    assert service._proxy_for_platform("bilibili") is None
    assert service._proxy_for_platform("kuaishou") is None

    parser = ParserService(settings)
    assert parser._resolve_dns_for("tiktok") is False
    assert parser._resolve_dns_for("twitter") is False
    assert parser._resolve_dns_for("douyin") is True


def test_stream_headers_include_platform_referers() -> None:
    assert StreamService._headers_for_platform("douyin")["Referer"] == "https://www.douyin.com/"
    assert StreamService._headers_for_platform("bilibili")["Referer"] == "https://www.bilibili.com/"
    assert StreamService._headers_for_platform("kuaishou")["Referer"] == "https://www.kuaishou.com/"
    assert "Referer" not in StreamService._headers_for_platform("twitter")
