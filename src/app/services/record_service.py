"""Parse record persistence."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta, timezone

from app.core.settings import AppSettings

BEIJING_TIMEZONE = timezone(timedelta(hours=8))


class RecordService:
    def __init__(self, settings: AppSettings) -> None:
        self.path = settings.paths.records_file or settings.paths.logs_dir / "parse_records.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._max_file_bytes = settings.resources.records_max_file_bytes

    def append(self, *, url: str, platform: str, media_type: str, title: str, ip: str) -> None:
        now = time.time()
        beijing_time = datetime.fromtimestamp(now, UTC).astimezone(BEIJING_TIMEZONE)
        record = {
            "ts": int(now),
            "timestamp": beijing_time.strftime("%Y-%m-%d %H:%M:%S"),
            "url": url[:2048],
            "platform": platform,
            "type": media_type,
            "title": title[:300],
            "ip": ip,
            "location": "",
        }
        with self._lock:
            if self._max_file_bytes > 0 and self.path.exists() and self.path.stat().st_size >= self._max_file_bytes:
                rotated = self.path.with_suffix(self.path.suffix + ".1")
                rotated.unlink(missing_ok=True)
                self.path.replace(rotated)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_records(self, platform: str = "", media_type: str = "", limit: int = 200) -> list[dict]:
        if not self.path.exists():
            return []
        records: deque[dict] = deque(maxlen=limit)
        with self._lock, self.path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if platform and item.get("platform") != platform:
                    continue
                if media_type and item.get("type") != media_type:
                    continue
                records.append(item)
        return list(reversed(records))
