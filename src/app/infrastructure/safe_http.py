"""HTTP helpers that revalidate every redirect before connecting."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from .url_safety import validate_url


def safe_get(url: str, *, max_redirects: int = 5, resolve_dns: bool = True, **kwargs) -> httpx.Response:
    kwargs.pop("follow_redirects", None)
    kwargs.setdefault("trust_env", False)
    current = validate_url(url, resolve_dns=resolve_dns).normalized
    for redirect_count in range(max_redirects + 1):
        response = httpx.get(current, follow_redirects=False, **kwargs)
        if not response.is_redirect:
            return response
        location = response.headers.get("location", "")
        response.close()
        if not location:
            raise httpx.HTTPError("Redirect response is missing Location")
        if redirect_count >= max_redirects:
            raise httpx.TooManyRedirects("Too many redirects")
        current = validate_url(str(httpx.URL(current).join(location)), resolve_dns=resolve_dns).normalized
    raise httpx.TooManyRedirects("Too many redirects")


@contextmanager
def safe_stream(url: str, *, max_redirects: int = 5, resolve_dns: bool = True, **kwargs) -> Iterator[httpx.Response]:
    kwargs.pop("follow_redirects", None)
    kwargs.setdefault("trust_env", False)
    headers = kwargs.pop("headers", None)
    current = validate_url(url, resolve_dns=resolve_dns).normalized
    client = httpx.Client(follow_redirects=False, **kwargs)
    response: httpx.Response | None = None
    try:
        for redirect_count in range(max_redirects + 1):
            response = client.send(client.build_request("GET", current, headers=headers), stream=True)
            if not response.is_redirect:
                yield response
                return
            location = response.headers.get("location", "")
            response.close()
            response = None
            if not location:
                raise httpx.HTTPError("Redirect response is missing Location")
            if redirect_count >= max_redirects:
                raise httpx.TooManyRedirects("Too many redirects")
            current = validate_url(str(httpx.URL(current).join(location)), resolve_dns=resolve_dns).normalized
        raise httpx.TooManyRedirects("Too many redirects")
    finally:
        if response is not None:
            response.close()
        client.close()
