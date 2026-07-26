"""Session tokens, client IP handling, and response headers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from .settings import AppSettings


@dataclass(frozen=True)
class SessionToken:
    subject: str
    purpose: str
    issued_bucket: int


ADMIN_COOKIE_NAME = "fzp_admin_session"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


@dataclass(frozen=True, slots=True)
class AdminSession:
    username: str
    issued_at: int
    expires_at: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_admin_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Admin password must contain at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64encode(salt)}${_b64encode(derived)}"


def verify_admin_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(derived, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def _admin_secret(settings: AppSettings) -> str:
    return settings.security.admin_session_secret or settings.security.session_secret


def make_admin_session_token(settings: AppSettings, username: str, *, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = {
        "sub": username,
        "iat": issued_at,
        "exp": issued_at + settings.security.admin_session_ttl_seconds,
        "purpose": "admin",
        "nonce": secrets.token_urlsafe(8),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(_admin_secret(settings).encode(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def verify_admin_session_token(settings: AppSettings, token: str, *, now: int | None = None) -> AdminSession | None:
    try:
        encoded, provided_signature = token.split(".", 1)
        expected_signature = hmac.new(
            _admin_secret(settings).encode(), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(provided_signature)):
            return None
        payload: dict[str, Any] = json.loads(_b64decode(encoded))
        current_time = int(time.time()) if now is None else now
        if payload.get("purpose") != "admin":
            return None
        if not hmac.compare_digest(str(payload.get("sub", "")), settings.security.admin_user):
            return None
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
        if issued_at > current_time + 30 or expires_at <= current_time:
            return None
        return AdminSession(settings.security.admin_user, issued_at, expires_at)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def is_trusted_admin_origin(request: Request, settings: AppSettings) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin.rstrip("/") in settings.security.admin_trusted_origins


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
        "font-src 'self'; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}
