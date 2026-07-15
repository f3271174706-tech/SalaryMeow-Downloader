from __future__ import annotations

import httpx

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


def test_record_can_use_old_admin_compatible_shared_file(tmp_path) -> None:
    shared = tmp_path / "legacy" / "parse_records.jsonl"
    settings = AppSettings.model_validate(
        {"paths": {"records_file": shared}, "resources": {"records_max_file_bytes": 0}}
    )
    service = RecordService(settings)

    service.append(
        url="https://www.douyin.com/video/1",
        platform="douyin",
        media_type="video",
        title="shared",
        ip="203.0.113.1",
    )
    record = service.list_records(limit=1)[0]

    assert service.path == shared
    assert record["timestamp"]
    assert record["location"] == ""
    assert record["ts"] > 0


def test_record_resolves_and_caches_public_ip_location(tmp_path, monkeypatch) -> None:
    settings = AppSettings.model_validate({"paths": {"logs_dir": tmp_path}})
    service = RecordService(settings)
    calls = 0

    def fake_get(url: str, **kwargs) -> httpx.Response:
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={"country": "中国", "region": "广东", "city": "深圳"},
            request=request,
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    for index in range(2):
        service.append(
            url=f"https://example.test/{index}",
            platform="test",
            media_type="video",
            title="location",
            ip="8.8.8.8",
        )

    assert service.list_records(limit=1)[0]["location"] == "中国 广东 深圳"
    assert calls == 1
