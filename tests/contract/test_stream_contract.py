from __future__ import annotations

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.api.dependencies import get_stream_service, require_invite_session, stream_limit
from app.infrastructure.rate_limit import AsyncConcurrencyLimit
from app.main import create_app


def test_stream_limit_is_held_for_response_body(monkeypatch) -> None:
    monkeypatch.setenv("DOUYIN_SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("DOUYIN_INVITE_CODES", "code")
    limit = AsyncConcurrencyLimit(1)

    class FakeStreamService:
        async def stream(self, request, video_url: str, quality: str) -> StreamingResponse:
            async def body():
                assert limit.active == 1
                yield b"ok"

            return StreamingResponse(body(), media_type="video/mp4")

    app = create_app()
    app.dependency_overrides[require_invite_session] = lambda: None
    app.dependency_overrides[get_stream_service] = FakeStreamService
    app.dependency_overrides[stream_limit] = lambda: limit

    with TestClient(app) as client:
        response = client.get("/api/stream", params={"video_url": "https://video.twimg.com/test.mp4"})

    assert response.status_code == 200
    assert response.content == b"ok"
    assert limit.active == 0
