"""Stream API route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.dependencies import get_stream_service, require_invite_session, stream_limit
from app.infrastructure.rate_limit import AsyncConcurrencyLimit, ConcurrencyLimitExceeded
from app.services.stream_service import StreamService

router = APIRouter(prefix="/api", tags=["stream"], dependencies=[Depends(require_invite_session)])


@router.get("/stream")
async def stream_video(
    request: Request,
    video_url: str = Query(..., max_length=4096),
    quality: str = Query("1080p", max_length=20),
    service: StreamService = Depends(get_stream_service),
    limit: AsyncConcurrencyLimit = Depends(stream_limit),
) -> StreamingResponse:
    acquired = False
    try:
        await limit.acquire()
        acquired = True
        response = await service.stream(request, video_url=video_url, quality=quality)
        previous_background = response.background

        async def release_slot() -> None:
            try:
                if previous_background is not None:
                    await previous_background()
            finally:
                limit.release()

        response.background = BackgroundTask(release_slot)
        acquired = False
        return response
    except ConcurrencyLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    finally:
        if acquired:
            limit.release()
