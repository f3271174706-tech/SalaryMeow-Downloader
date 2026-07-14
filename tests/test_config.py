"""配置模块测试"""

import pytest

from douyin_downloader.config import Config, _deep_merge


class TestDeepMerge:
    """测试深度合并函数"""

    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 20, "z": 30}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}

    def test_empty_override(self):
        base = {"a": 1}
        override = {}
        result = _deep_merge(base, override)
        assert result == {"a": 1}


class TestConfig:
    """测试配置类"""

    def test_singleton(self):
        c1 = Config()
        c2 = Config()
        assert c1 is c2

    def test_get_simple(self):
        config = Config()
        # 应该能获取默认配置
        assert config.get("network.timeout") == 30

    def test_get_with_default(self):
        config = Config()
        assert config.get("nonexistent.key", "default") == "default"

    def test_get_nested(self):
        config = Config()
        assert config.get("network.connect_timeout") == 10

    def test_get_timeout(self):
        config = Config()
        timeout = config.get_timeout()
        assert "connect" in timeout
        assert "read" in timeout
