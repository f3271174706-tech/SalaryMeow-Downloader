from __future__ import annotations

from app.legacy import downloader


class _JsonResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload


def test_bilibili_prefers_allowlisted_backup_over_dynamic_mcdn() -> None:
    selected = downloader._select_bilibili_video_url(
        {
            "url": "https://random.edge.mountaintoys.cn:4483/video.mp4",
            "backup_url": [
                "https://upos-sz-estgcos.bilivideo.com/video.mp4",
                "https://upos-sz-mirrorcos.bilivideo.com/video.mp4",
            ],
        }
    )

    assert selected == "https://upos-sz-estgcos.bilivideo.com/video.mp4"


def test_bilibili_thumbnail_is_upgraded_to_https(monkeypatch) -> None:
    responses = iter(
        [
            _JsonResponse(
                {
                    "code": 0,
                    "data": {
                        "title": "video",
                        "cid": 1,
                        "pic": "http://i0.hdslb.com/cover.jpg",
                        "duration": 10,
                    },
                }
            ),
            _JsonResponse(
                {
                    "code": 0,
                    "data": {"durl": [{"url": "https://upos-sz-estgcos.bilivideo.com/video.mp4"}]},
                }
            ),
        ]
    )
    monkeypatch.setattr(downloader.httpx, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(downloader.config, "get_cookie", lambda _platform: "")

    result = downloader._extract_bilibili("https://www.bilibili.com/video/BV1ENNS6DEcW/")

    assert result["thumbnail"] == "https://i0.hdslb.com/cover.jpg"
