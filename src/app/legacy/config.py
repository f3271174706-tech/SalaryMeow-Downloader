"""
配置管理模块
从 config.yaml 读取配置，提供统一的配置访问接口
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

import yaml

# 项目根目录。默认指向本次重构仓库根目录，也可以通过环境变量覆盖。
BASE_DIR = Path(os.environ.get("DOUYIN_APP_ROOT", Path(__file__).resolve().parents[3]))

# 默认配置（当 config.yaml 不存在时使用）
DEFAULT_CONFIG = {
    "network": {
        "timeout": 30,
        "connect_timeout": 10,
        "read_timeout": 300,
        "proxy": "",
        "max_retries": 3,
        "retry_delay_base": 1,
    },
    "user_agent": {
        "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    },
    "cookies": {
        "douyin": "",
        "tiktok": "",
        "bilibili": "",
        "twitter": "",
        "kuaishou": "",
    },
    "logging": {
        "level": "INFO",
        "file": "logs/downloader.log",
        "max_size": 10,
        "backup_count": 5,
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    },
    "download": {
        "directory": "downloads",
        "cleanup_delay": 600,
        "startup_cleanup_age": 1800,
        "chunk_size": 65536,
    },
    "cache": {
        "enabled": True,
        "ttl": 600,
    },
    "api": {
        "enabled": True,
        "timeout": 15,
        "fallback_to_crawler": False,
    },
    "platforms": {
        "douyin": {
            "enable_playwright": True,
            "playwright_timeout": 15000,
        },
        "tiktok": {
            "parser_url": "https://ssstiktok.cc/",
        },
    },
}


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """深度合并两个字典，override 中的值会覆盖 base 中的值"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """配置管理类（单例模式）"""

    _instance = None
    _config = None
    _cookie_failed = {}  # 记录失败的 Cookie

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._load_config()

    def _load_config(self):
        """加载配置文件"""
        config_path = Path(os.environ.get("DOUYIN_CONFIG", BASE_DIR / "config.yaml"))

        # 从默认配置开始
        self._config = DEFAULT_CONFIG.copy()

        # 如果配置文件存在，读取并合并
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                self._config = _deep_merge(self._config, user_config)
            except Exception as e:
                print(f"[config] 警告: 读取 config.yaml 失败: {e}", file=sys.stderr)

        # Runtime directories are created by the typed application settings.
        # Config loading stays side-effect free so the application directory
        # can remain read-only under systemd.

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点号分隔的路径
        例如: config.get("network.timeout")
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def get_cookie(self, platform: str) -> str:
        """获取指定平台的 Cookie（随机选择可用的）"""
        import random
        cookies = self.get(f"cookies.{platform}", "")
        if isinstance(cookies, list):
            # 过滤掉空 Cookie 和之前失败的
            failed = self._cookie_failed.get(platform, set())
            valid = [c for i, c in enumerate(cookies) if c and i not in failed]
            if not valid:
                # 所有都失败过，重置
                self._cookie_failed[platform] = set()
                valid = [c for c in cookies if c]
            if valid:
                return random.choice(valid)
            return ""
        return cookies if cookies else ""

    def mark_cookie_failed(self, platform: str, cookie: str) -> None:
        """标记 Cookie 失败（解析失败时调用）"""
        cookies = self.get(f"cookies.{platform}", [])
        if isinstance(cookies, list) and cookie in cookies:
            idx = cookies.index(cookie)
            if platform not in self._cookie_failed:
                self._cookie_failed[platform] = set()
            self._cookie_failed[platform].add(idx)
            logger.info(f"[config] 标记 {platform} Cookie #{idx + 1} 失败")

    def rotate_cookie(self, platform: str, failed_cookie: str = "") -> str:
        """Mark the failed Cookie and select another configured value."""
        if failed_cookie:
            self.mark_cookie_failed(platform, failed_cookie)

        cookies = self.get(f"cookies.{platform}", "")
        if isinstance(cookies, list):
            import random

            alternatives = [cookie for cookie in cookies if cookie and cookie != failed_cookie]
            if alternatives:
                return random.choice(alternatives)
        return self.get_cookie(platform)

    def get_headers(self, platform: str = "", include_cookie: bool = True) -> Dict[str, str]:
        """
        获取请求头

        Args:
            platform: 平台名称（douyin, tiktok, bilibili, twitter, kuaishou）
            include_cookie: 是否包含 Cookie
        """
        headers = {
            "User-Agent": self.get("user_agent.mobile"),
        }

        # 添加 Referer
        referer_map = {
            "douyin": "https://www.douyin.com/",
            "tiktok": "https://www.tiktok.com/",
            "bilibili": "https://www.bilibili.com/",
            "twitter": "https://x.com/",
            "kuaishou": "https://www.kuaishou.com/",
        }
        if platform in referer_map:
            headers["Referer"] = referer_map[platform]

        # 添加 Cookie
        if include_cookie and platform:
            cookie = self.get_cookie(platform)
            if cookie:
                headers["Cookie"] = cookie

        return headers

    def get_timeout(self) -> Dict[str, int]:
        """获取超时配置"""
        return {
            "connect": self.get("network.connect_timeout", 10),
            "read": self.get("network.read_timeout", 300),
            "write": 10,
            "pool": 10,
        }

    def get_proxy(self) -> Optional[str]:
        """获取代理配置"""
        proxy = self.get("network.proxy", "")
        return proxy if proxy else None

    def reload(self):
        """重新加载配置文件"""
        self._config = None
        self._load_config()

    def __repr__(self):
        redacted = _deep_merge({}, self._config)
        cookies = redacted.get("cookies", {})
        if isinstance(cookies, dict):
            for key, value in list(cookies.items()):
                if isinstance(value, list):
                    cookies[key] = ["***" if item else "" for item in value]
                elif value:
                    cookies[key] = "***"
        return f"Config({redacted})"


# 全局配置实例
config = Config()


def setup_logging() -> logging.Logger:
    """
    设置日志系统

    Returns:
        logging.Logger: 配置好的 logger
    """
    from logging.handlers import RotatingFileHandler

    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    log_format = log_config.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log_file = log_config.get("file", "")
    max_size = log_config.get("max_size", 10) * 1024 * 1024  # 转换为字节
    backup_count = log_config.get("backup_count", 5)

    # 创建 formatter
    formatter = logging.Formatter(log_format)

    # 获取 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有的 handler（避免重复添加）
    root_logger.handlers.clear()

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件 handler（如果配置了日志文件）
    if log_file:
        configured_logs_dir = os.environ.get("DOUYIN_LOGS_DIR")
        log_path = (
            Path(configured_logs_dir) / Path(log_file).name if configured_logs_dir else BASE_DIR / log_file
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_size,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


# 便捷函数
def get_config() -> Config:
    """获取全局配置实例"""
    return config


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger"""
    return logging.getLogger(name)
