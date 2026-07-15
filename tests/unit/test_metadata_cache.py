from __future__ import annotations

from app.infrastructure import metadata_cache
from app.infrastructure.metadata_cache import MetadataCache


def test_metadata_cache_expires_and_returns_a_copy(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr(metadata_cache.time, "monotonic", lambda: now[0])
    cache = MetadataCache(ttl_seconds=600, max_entries=2)
    value = {"title": "first", "nested": {"type": "video"}}

    cache.set("url", value)
    result = cache.get("url")
    assert result == value
    assert result is not None
    result["nested"]["type"] = "changed"
    assert cache.get("url")["nested"]["type"] == "video"

    now[0] += 600
    assert cache.get("url") is None


def test_metadata_cache_evicts_least_recently_used() -> None:
    cache = MetadataCache(ttl_seconds=600, max_entries=2)
    cache.set("one", {"value": 1})
    cache.set("two", {"value": 2})
    assert cache.get("one") == {"value": 1}
    cache.set("three", {"value": 3})

    assert cache.get("two") is None
    assert cache.get("one") == {"value": 1}
    assert cache.get("three") == {"value": 3}
