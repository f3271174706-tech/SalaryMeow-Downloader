"""Download API route."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.dependencies import download_limit, get_download_service, require_invite_session
from app.infrastructure.rate_limit import ConcurrencyLimit, ConcurrencyLimitExceeded
from app.services.download_service import DownloadService, DownloadTooLargeError, InsufficientStorageError

router = APIRouter(prefix="/api", tags=["download"], dependencies=[Depends(require_invite_session)])
logger = logging.getLogger(__name__)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    quality: str = "1080p"
    type: str = "video"
    image_index: int = 0
    live_photo_format: bool = False
    live_photo_index: int = 0


@router.post("/download")
def download_video_api(
    payload: DownloadRequest,
    service: DownloadService = Depends(get_download_service),
    limit: ConcurrencyLimit = Depends(download_limit),
) -> FileResponse:
    try:
        with limit.hold():
            file_path, filename = service.download(
                url=payload.url,
                quality=payload.quality,
                media_type=payload.type,
                image_index=payload.image_index,
                live_photo_format=payload.live_photo_format,
                live_photo_index=payload.live_photo_index,
            )
    except ConcurrencyLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except DownloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail="下载内容超过大小限制") from exc
    except InsufficientStorageError as exc:
        raise HTTPException(status_code=507, detail="服务器存储空间不足") from exc
    except Exception as exc:
        logger.warning("Download failed", exc_info=True)
        raise HTTPException(status_code=400, detail="下载失败") from exc

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    media_type = {
        "mp3": "audio/mpeg",
        "zip": "application/zip",
        "webp": "image/webp",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }.get(suffix, "video/mp4")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}",
            "X-File-Size": str(os.path.getsize(file_path)),
            "Access-Control-Expose-Headers": "X-File-Size, Content-Disposition",
        },
    )
