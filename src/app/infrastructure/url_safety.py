"""Shared URL validation for parsing, downloading, streaming, redirects, and tools."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "douyin": (
        "douyin.com",
        "iesdouyin.com",
        "douyinpic.com",
        "douyinvod.com",
        "douyincdn.com",
        "snssdk.com",
        "bytecdn.cn",
        "bytedance.com",
        "zjcdn.com",
        "bdstatic.com",
        "pstatp.com",
        "douyinstatic.com",
    ),
    "tiktok": ("tiktok.com", "tiktokv.com", "ttwstatic.com", "tiktokcdn.com", "ssstiktok.cc", "snaptik.app"),
    "twitter": (
        "twitter.com",
        "x.com",
        "t.co",
        "twimg.com",
        "twttr.com",
        "pscp.tv",
        "tweetdeck.com",
        "video.twimg.com",
        "api.fxtwitter.com",
        "fxtwitter.com",
    ),
    "bilibili": (
        "bilibili.com",
        "b23.tv",
        "bilivideo.com",
        "hdslb.com",
        "bilivideo.cn",
        # Bilibili's play API can return this specific Akamai mirror.
        "upos-hz-mirrorakam.akamaized.net",
    ),
    "kuaishou": (
        "kuaishou.com",
        "gifshow.com",
        "chenzhongtech.com",
        "yximgs.com",
        "kwaicdn.com",
        "kwaicdn2.com",
        "oskwai.com",
    ),
}

CLOUD_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


class UrlSafetyError(ValueError):
    """Raised when a URL is not safe for server-side fetching."""


@dataclass(frozen=True)
class SafeUrl:
    raw: str
    normalized: str
    hostname: str
    platform: str


def normalize_input_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise UrlSafetyError("URL is empty")
    if len(value) > 4096:
        raise UrlSafetyError("URL is too long")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def _hostname_matches(hostname: str, domain: str) -> bool:
    hostname = hostname.rstrip(".").lower()
    domain = domain.lower()
    return hostname == domain or hostname.endswith("." + domain)


def detect_platform_from_hostname(hostname: str) -> str | None:
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(_hostname_matches(hostname, domain) for domain in domains):
            return platform
    return None


def _is_forbidden_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or ip in CLOUD_METADATA_IPS
    )


def _resolve_host(hostname: str) -> set[str]:
    results: set[str] = set()
    for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
        if family in {socket.AF_INET, socket.AF_INET6}:
            results.add(str(sockaddr[0]))
    return results


def validate_url(value: str, *, platform: str | None = None, resolve_dns: bool = True) -> SafeUrl:
    normalized = normalize_input_url(value)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise UrlSafetyError("Only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise UrlSafetyError("Userinfo is not allowed in URLs")
    if not parsed.hostname:
        raise UrlSafetyError("URL hostname is required")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise UrlSafetyError("Malformed URL port") from exc

    hostname = parsed.hostname.rstrip(".").lower()
    detected = detect_platform_from_hostname(hostname)
    if platform and detected != platform:
        raise UrlSafetyError("URL does not match the requested platform")
    if not detected:
        raise UrlSafetyError("URL hostname is not in the platform allowlist")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if resolve_dns:
            for ip in _resolve_host(hostname):
                if _is_forbidden_ip(ip):
                    raise UrlSafetyError("URL resolves to a forbidden IP address") from None
    else:
        if _is_forbidden_ip(hostname):
            raise UrlSafetyError("IP address is not allowed")

    return SafeUrl(raw=value, normalized=normalized, hostname=hostname, platform=detected)
