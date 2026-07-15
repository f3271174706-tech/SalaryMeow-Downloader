"""Streaming proxy with Range support and redirect URL validation."""

from __future__ import annotations

import logging
import re

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.settings import AppSettings
from app.infrastructure.url_safety import UrlSafetyError, validate_url
from app.legacy.downloader import MOBILE_UA, apply_quality


class StreamService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def _proxy_for_platform(self, platform: str) -> str | None:
        if platform in {"tiktok", "twitter"}:
            return self.settings.network.proxy or None
        return None

    async def stream(self, request: Request, video_url: str, quality: str = "1080p") -> StreamingResponse:
        try:
            safe = validate_url(video_url)
        except UrlSafetyError as exc:
            raise HTTPException(status_code=400, detail="媒体地址不安全") from exc
        target = safe.normalized
        if safe.platform == "douyin":
            target = apply_quality(target, quality)

        headers = {"User-Agent": MOBILE_UA}
        if safe.platform == "bilibili":
            headers["Referer"] = "https://www.bilibili.com/"
        elif safe.platform == "kuaishou":
            headers["Referer"] = "https://www.kuaishou.com/"
        range_header = request.headers.get("range")
        if range_header:
            if not re.fullmatch(r"bytes=\d*-\d*", range_header.strip(), flags=re.IGNORECASE):
                raise HTTPException(status_code=400, detail="无效的 Range 请求")
            headers["Range"] = range_header

        timeout = httpx.Timeout(
            connect=self.settings.resources.request_timeout_seconds,
            read=self.settings.resources.stream_read_timeout_seconds,
            write=10,
            pool=10,
        )
        client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            proxy=self._proxy_for_platform(safe.platform),
        )
        try:
            current_url = target
            for _ in range(self.settings.resources.max_redirects + 1):
                for attempt in range(2):
                    try:
                        response = await client.send(
                            client.build_request("GET", current_url, headers=headers), stream=True
                        )
                    except httpx.TransportError:
                        if attempt:
                            raise
                        continue
                    if response.status_code < 500 or attempt:
                        break
                    await response.aclose()
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    await response.aclose()
                    if not location:
                        raise HTTPException(status_code=502, detail="上游重定向缺少 Location")
                    safe_redirect = validate_url(
                        str(httpx.URL(current_url).join(location)), platform=safe.platform
                    )
                    current_url = safe_redirect.normalized
                    continue
                break
            else:
                raise HTTPException(status_code=400, detail="重定向次数过多")

            if response.status_code >= 400:
                await response.aclose()
                raise HTTPException(status_code=502, detail=f"源返回 {response.status_code}")

            content_length_raw = response.headers.get("content-length")
            if content_length_raw:
                try:
                    content_length = int(content_length_raw)
                except ValueError:
                    content_length = 0
                if content_length > self.settings.resources.max_stream_bytes:
                    await response.aclose()
                    raise HTTPException(status_code=413, detail="媒体超过流式传输大小限制")

            resp_headers = {
                key: value
                for key in ("content-type", "content-length", "content-range", "accept-ranges")
                if (value := response.headers.get(key))
            }

            async def iterator():
                total = 0
                try:
                    async for chunk in response.aiter_bytes(65536):
                        total += len(chunk)
                        if total > self.settings.resources.max_stream_bytes:
                            break
                        yield chunk
                finally:
                    await response.aclose()
                    await client.aclose()

            status_code = 206 if range_header and response.status_code == 206 else 200
            return StreamingResponse(iterator(), status_code=status_code, headers=resp_headers)
        except HTTPException:
            await client.aclose()
            raise
        except Exception as exc:
            logging.getLogger(__name__).warning("Streaming connection failed", exc_info=True)
            await client.aclose()
            raise HTTPException(status_code=502, detail="流式连接失败") from exc
