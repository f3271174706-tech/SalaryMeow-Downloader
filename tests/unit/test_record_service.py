from __future__ import annotations

from app.core.settings import AppSettings
from app.services.record_service import RecordService


def test_record_listing_is_bounded(tmp_path) -> None:
    settings = AppSettings.model_validate({"paths": {"logs_dir": tmp_path}})
    service = RecordService(settings)
    for index in range(5):
        service.append(
            url=f"https://example.test/{index}", platform="test", media_type="video", title=str(index), ip="127.0.0.1"
        )

    records = service.list_records(limit=2)

    assert [record["title"] for record in records] == ["4", "3"]
