"""Parse API route."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import (
    get_parser_service,
    get_preload_service,
    get_record_service,
    parse_limit,
    require_invite_session,
    settings_dep,
)
from app.core.security import get_client_ip
from app.core.settings import AppSettings
from app.infrastructure.rate_limit import ConcurrencyLimit, ConcurrencyLimitExceeded
from app.services.parser_service import ParserService
from app.services.preload_service import PreloadService
from app.services.record_service import RecordService

router = APIRouter(prefix="/api", tags=["parse"], dependencies=[Depends(require_invite_session)])
logger = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


@router.post("/parse")
def parse_video(
    payload: ParseRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    parser: ParserService = Depends(get_parser_service),
    preloader: PreloadService = Depends(get_preload_service),
    records: RecordService = Depends(get_record_service),
    limit: ConcurrencyLimit = Depends(parse_limit),
    settings: AppSettings = Depends(settings_dep),
) -> dict:
    try:
        with limit.hold():
            info = parser.parse(payload.url)
    except ConcurrencyLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Parse failed", exc_info=True)
        raise HTTPException(status_code=400, detail="解析失败") from exc

    media_type = info.get("type", "video")
    platform = info.get("platform", "unknown")
    title = info.get("title", "")
    background_tasks.add_task(
        records.append,
        url=payload.url,
        platform=platform,
        media_type=media_type,
        title=title,
        ip=get_client_ip(request, settings),
    )
    preloader.schedule(payload.url, info)

    result = {
        "success": True,
        "title": title,
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration", 0),
        "platform": platform,
        "type": media_type,
    }
    if media_type == "photo":
        result.update({"images": info.get("images", []), "video_url": "", "music_url": info.get("music_url", "")})
    elif media_type == "live_photo":
        result.update(
            {
                "video_url": info.get("video_url", ""),
                "video_urls": info.get("video_urls", []),
                "images": info.get("images", []),
                "music_url": info.get("music_url", ""),
            }
        )
    else:
        result.update({"video_url": info.get("video_url", ""), "m3u8_url": info.get("m3u8_url", "")})
    return result
