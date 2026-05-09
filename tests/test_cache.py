from pathlib import Path

import pytest
from ytmuxiris.utils.cache import APICache


@pytest.fixture()
def cache(tmp_path: Path) -> APICache:
    return APICache(str(tmp_path))


def test_set_and_get(cache: APICache) -> None:
    cache.set("key1", {"data": 42})
    result = cache.get("key1", ttl=60)
    assert result == {"data": 42}


def test_miss_returns_none(cache: APICache) -> None:
    assert cache.get("missing", ttl=60) is None


def test_ttl_expiry(cache: APICache) -> None:
    cache.set("key2", "value")
    result = cache.get("key2", ttl=0)  # TTL=0 means always expired
    assert result is None


def test_invalidate(cache: APICache) -> None:
    cache.set("key3", "hello")
    cache.invalidate("key3")
    assert cache.get("key3", ttl=60) is None


def test_invalidate_library(cache: APICache) -> None:
    k1 = "library_songs_abc"
    k2 = "library_albums_def"
    k3 = "search_xyz"
    cache.set(k1, [1, 2])
    cache.set(k2, [3, 4])
    cache.set(k3, [5])
    cache.invalidate_library()
    assert cache.get(k1, ttl=60) is None
    assert cache.get(k2, ttl=60) is None
    assert cache.get(k3, ttl=60) == [5]


def test_make_key_deterministic(cache: APICache) -> None:
    k1 = APICache.make_key("search", q="hello", limit=20)
    k2 = APICache.make_key("search", limit=20, q="hello")
    assert k1 == k2


def test_disk_persistence(tmp_path: Path) -> None:
    cache1 = APICache(str(tmp_path))
    cache1.set("persist_key", {"x": 1})

    cache2 = APICache(str(tmp_path))
    result = cache2.get("persist_key", ttl=3600)
    assert result == {"x": 1}
