"""Session tokens, client IP handling, and response headers."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from dataclasses import dataclass

from fastapi import Request

from .settings import AppSettings


@dataclass(frozen=True)
class SessionToken:
    subject: str
    purpose: str
    issued_bucket: int


def make_session_token(settings: AppSettings, subject: str, purpose: str, ttl_seconds: int) -> str:
    issued_at = int(time.time())
    payload = f"{purpose}:{subject}:{issued_at}"
    sig = hmac.new(settings.security.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{subject}:{issued_at}:{sig}"


def verify_session_token(settings: AppSettings, token: str, subject: str, purpose: str, ttl_seconds: int) -> bool:
    if not token:
        return False
    try:
        token_subject, issued_at_raw, sig = token.split(":", 2)
        if not hmac.compare_digest(token_subject, subject):
            return False
        issued_at = int(issued_at_raw)
    except (ValueError, TypeError):
        return False

    age = int(time.time()) - issued_at
    if age < 0 or age > ttl_seconds:
        return False
    payload = f"{purpose}:{subject}:{issued_at}"
    expected = hmac.new(settings.security.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def verify_invite_code(settings: AppSettings, code: str) -> bool:
    return any(hmac.compare_digest(code, allowed) for allowed in settings.security.invite_codes)


def _ip_in_cidrs(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def get_client_ip(request: Request, settings: AppSettings) -> str:
    direct_ip = request.client.host if request.client else ""
    if not settings.security.trust_proxy_headers:
        return direct_ip
    if not settings.security.trusted_proxy_cidrs:
        return direct_ip
    if not _ip_in_cidrs(direct_ip, settings.security.trusted_proxy_cidrs):
        return direct_ip
    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip and _is_valid_ip(cf_ip):
        return cf_ip
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        forwarded_ip = xff.split(",", 1)[0].strip()
        if _is_valid_ip(forwarded_ip):
            return forwarded_ip
    return direct_ip


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https: blob:; "
        "media-src 'self' https: blob:; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}
