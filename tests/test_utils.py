"""工具函数测试"""

import pytest

from douyin_downloader.utils import RequestError, detect_platform, extract_url


class TestDetectPlatform:
    """测试平台检测"""

    def test_douyin(self):
        assert detect_platform("https://www.douyin.com/video/123") == "douyin"
        assert detect_platform("https://v.douyin.com/abc") == "douyin"

    def test_twitter(self):
        assert detect_platform("https://twitter.com/user/status/123") == "twitter"
        assert detect_platform("https://x.com/user/status/123") == "twitter"

    def test_tiktok(self):
        assert detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"

    def test_bilibili(self):
        assert detect_platform("https://www.bilibili.com/video/BV123") == "bilibili"
        assert detect_platform("https://b23.tv/abc") == "bilibili"

    def test_kuaishou(self):
        assert detect_platform("https://www.kuaishou.com/short-video/123") == "kuaishou"

    def test_unknown(self):
        assert detect_platform("https://example.com/video") is None


class TestExtractUrl:
    """测试 URL 提取"""

    def test_plain_url(self):
        url = extract_url("https://www.douyin.com/video/123")
        assert url == "https://www.douyin.com/video/123"

    def test_url_with_text(self):
        url = extract_url("看看这个视频 https://v.douyin.com/abc 分享给你")
        assert "https://v.douyin.com/abc" in url

    def test_short_url(self):
        url = extract_url("v.douyin.com/abc")
        assert url.startswith("https://")

    def test_whitespace(self):
        url = extract_url("  https://example.com  ")
        assert url == "https://example.com"


class TestRequestError:
    """测试请求异常"""

    def test_create(self):
        err = RequestError("test error", status_code=500, url="https://example.com")
        assert str(err) == "test error"
        assert err.status_code == 500
        assert err.url == "https://example.com"
