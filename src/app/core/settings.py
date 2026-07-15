"""Typed settings loaded from YAML and environment variables."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class SecuritySettings(BaseModel):
    app_env: str = Field(default="development")
    invite_auth_enabled: bool = True
    session_secret: str = Field(default="")
    invite_codes: list[str] = Field(default_factory=list)
    invite_session_ttl_seconds: int = 7 * 24 * 3600
    admin_user: str = "admin"
    admin_password: str = ""
    admin_external_url: str = ""
    admin_session_ttl_seconds: int = 24 * 3600
    trust_proxy_headers: bool = False
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    secure_cookies: bool = False


class ResourceSettings(BaseModel):
    parse_concurrency: int = 4
    download_concurrency: int = 2
    stream_concurrency: int = 8
    max_request_url_length: int = 4096
    max_stream_bytes: int = 1024 * 1024 * 1024
    max_download_bytes: int = 1024 * 1024 * 1024
    request_timeout_seconds: int = 30
    stream_read_timeout_seconds: int = 300
    max_redirects: int = 5
    preload_enabled: bool = False
    metadata_cache_ttl_seconds: int = 600
    metadata_cache_max_entries: int = 500
    preload_platforms: list[str] = Field(default_factory=lambda: ["douyin"])
    preload_max_duration_seconds: int = 180
    preload_max_bytes: int = 100 * 1024 * 1024
    preload_cache_max_bytes: int = 512 * 1024 * 1024
    preload_cache_max_entries: int = 20
    preload_concurrency: int = 1
    preload_wait_seconds: float = 2.0
    records_max_file_bytes: int = 20 * 1024 * 1024
    f2_prewarm_enabled: bool = True


class PathSettings(BaseModel):
    data_dir: Path = PROJECT_ROOT / "var"
    downloads_dir: Path = PROJECT_ROOT / "var" / "downloads"
    logs_dir: Path = PROJECT_ROOT / "var" / "logs"
    records_file: Path | None = None
    web_static_dir: Path = PROJECT_ROOT / "web" / "static"
    web_templates_dir: Path = PROJECT_ROOT / "web" / "templates"


class NetworkSettings(BaseModel):
    proxy: str = ""


class AppSettings(BaseModel):
    title: str = "Douyin Downloader Refactored"
    host: str = "127.0.0.1"
    port: int = 9000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:9000", "http://localhost:9000"])
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    resources: ResourceSettings = Field(default_factory=ResourceSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    @property
    def is_production(self) -> bool:
        return self.security.app_env.lower() == "production"

    @property
    def admin_enabled(self) -> bool:
        return bool(self.security.admin_password)

    def validate_for_startup(self) -> list[str]:
        warnings: list[str] = []
        if self.security.admin_external_url:
            admin_url = urlparse(self.security.admin_external_url)
            if admin_url.scheme != "https" or not admin_url.hostname:
                raise RuntimeError("ADMIN_EXTERNAL_URL must be an absolute HTTPS URL")
        if self.is_production:
            if len(self.security.session_secret) < 32:
                raise RuntimeError("DOUYIN_SESSION_SECRET must be set to at least 32 characters in production")
            if self.security.invite_auth_enabled and not self.security.invite_codes:
                raise RuntimeError("DOUYIN_INVITE_CODES must be set in production")
            if not self.security.secure_cookies:
                raise RuntimeError("DOUYIN_SECURE_COOKIES must be true in production")
        elif not self.security.session_secret:
            self.security.session_secret = secrets.token_urlsafe(32)
            warnings.append(
                "Generated temporary development session secret; set DOUYIN_SESSION_SECRET for stable sessions."
            )
        return warnings

    def ensure_directories(self) -> None:
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _apply_env(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    security = dict(data.get("security", {}))
    resources = dict(data.get("resources", {}))
    network = dict(data.get("network", {}))
    paths = dict(data.get("paths", {}))

    env_map = {
        "DOUYIN_APP_ENV": (security, "app_env"),
        "DOUYIN_INVITE_AUTH_ENABLED": (security, "invite_auth_enabled"),
        "DOUYIN_SESSION_SECRET": (security, "session_secret"),
        "ADMIN_USER": (security, "admin_user"),
        "ADMIN_PASS": (security, "admin_password"),
        "ADMIN_EXTERNAL_URL": (security, "admin_external_url"),
        "DOUYIN_TRUST_PROXY_HEADERS": (security, "trust_proxy_headers"),
        "DOUYIN_SECURE_COOKIES": (security, "secure_cookies"),
        "DOUYIN_PRELOAD_ENABLED": (resources, "preload_enabled"),
        "DOUYIN_METADATA_CACHE_TTL_SECONDS": (resources, "metadata_cache_ttl_seconds"),
        "DOUYIN_METADATA_CACHE_MAX_ENTRIES": (resources, "metadata_cache_max_entries"),
        "DOUYIN_PRELOAD_MAX_DURATION_SECONDS": (resources, "preload_max_duration_seconds"),
        "DOUYIN_PRELOAD_MAX_BYTES": (resources, "preload_max_bytes"),
        "DOUYIN_PRELOAD_CACHE_MAX_BYTES": (resources, "preload_cache_max_bytes"),
        "DOUYIN_PRELOAD_CACHE_MAX_ENTRIES": (resources, "preload_cache_max_entries"),
        "DOUYIN_PRELOAD_CONCURRENCY": (resources, "preload_concurrency"),
        "DOUYIN_PRELOAD_WAIT_SECONDS": (resources, "preload_wait_seconds"),
        "DOUYIN_RECORDS_MAX_FILE_BYTES": (resources, "records_max_file_bytes"),
        "DOUYIN_F2_PREWARM_ENABLED": (resources, "f2_prewarm_enabled"),
        "DOUYIN_MAX_STREAM_BYTES": (resources, "max_stream_bytes"),
        "DOUYIN_MAX_DOWNLOAD_BYTES": (resources, "max_download_bytes"),
        "DOUYIN_DATA_DIR": (paths, "data_dir"),
        "DOUYIN_DOWNLOADS_DIR": (paths, "downloads_dir"),
        "DOUYIN_LOGS_DIR": (paths, "logs_dir"),
        "DOUYIN_RECORDS_FILE": (paths, "records_file"),
        "DOUYIN_HTTP_PROXY": (network, "proxy"),
        "DOUYIN_HOST": (data, "host"),
        "DOUYIN_PORT": (data, "port"),
    }
    for env_name, (target, key) in env_map.items():
        if env_name in os.environ:
            raw = os.environ[env_name]
            if raw.lower() in {"true", "false"}:
                target[key] = raw.lower() == "true"
            elif key in {
                "port",
                "max_stream_bytes",
                "max_download_bytes",
                "metadata_cache_ttl_seconds",
                "metadata_cache_max_entries",
                "preload_max_duration_seconds",
                "preload_max_bytes",
                "preload_cache_max_bytes",
                "preload_cache_max_entries",
                "preload_concurrency",
                "records_max_file_bytes",
            }:
                target[key] = int(raw)
            elif key == "preload_wait_seconds":
                target[key] = float(raw)
            elif key == "records_file" and not raw.strip():
                target[key] = None
            else:
                target[key] = raw

    if "DOUYIN_INVITE_CODES" in os.environ:
        security["invite_codes"] = _split_csv(os.environ["DOUYIN_INVITE_CODES"])
    if "DOUYIN_CORS_ORIGINS" in os.environ:
        data["cors_origins"] = _split_csv(os.environ["DOUYIN_CORS_ORIGINS"])
    if "DOUYIN_PRELOAD_PLATFORMS" in os.environ:
        resources["preload_platforms"] = _split_csv(os.environ["DOUYIN_PRELOAD_PLATFORMS"])
    if "DOUYIN_TRUSTED_PROXY_CIDRS" in os.environ:
        security["trusted_proxy_cidrs"] = _split_csv(os.environ["DOUYIN_TRUSTED_PROXY_CIDRS"])

    data["security"] = security
    data["resources"] = resources
    data["network"] = network
    data["paths"] = paths
    return data


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    config_path = Path(os.environ.get("DOUYIN_CONFIG", PROJECT_ROOT / "config.yaml"))
    data = _apply_env(_load_yaml(config_path))
    settings = AppSettings.model_validate(data)
    settings.ensure_directories()
    settings.validate_for_startup()
    os.environ.setdefault("DOUYIN_APP_ROOT", str(PROJECT_ROOT))
    os.environ.setdefault("DOUYIN_DOWNLOADS_DIR", str(settings.paths.downloads_dir))
    os.environ.setdefault("DOUYIN_MAX_DOWNLOAD_BYTES", str(settings.resources.max_download_bytes))
    return settings
