"""Admin API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_record_service, require_admin_session
from app.services.record_service import RecordService

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_session)])


@router.get("/overview")
def overview(record_service: RecordService = Depends(get_record_service)) -> dict[str, object]:
    summary = record_service.overview()
    platforms = summary["platforms"]
    platform_count = len(platforms) if isinstance(platforms, dict) else 0
    return {
        "greeting": "服务运行正常，以下是当前解析数据概览。",
        "stats": [
            {"label": "累计解析", "value": str(summary["total"]), "tone": "accent"},
            {"label": "今日解析", "value": str(summary["today"]), "tone": "success"},
            {"label": "已覆盖平台", "value": str(platform_count), "tone": "neutral"},
        ],
        "summary": summary,
    }


@router.get("/records")
def records(
    platform: str = Query("", max_length=50),
    type: str = Query("", max_length=50),
    limit: int = Query(200, ge=1, le=1000),
    record_service: RecordService = Depends(get_record_service),
) -> list[dict]:
    return record_service.list_records(platform=platform, media_type=type, limit=limit)
