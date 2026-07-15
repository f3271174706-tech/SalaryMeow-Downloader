from __future__ import annotations

from app.core.security import SECURITY_HEADERS


def test_csp_allows_only_the_cloudflare_insights_script_origin() -> None:
    policy = SECURITY_HEADERS["Content-Security-Policy"]

    assert "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com" in policy
