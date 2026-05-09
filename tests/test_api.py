from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ytmuxiris.api.auth import AuthManager
from ytmuxiris.api.ytmuxiris import YouTubeMusicAPI
from ytmuxiris.utils.cache import APICache


@pytest.fixture()
def cache(tmp_path: Path) -> APICache:
    return APICache(str(tmp_path))


@pytest.fixture()
def auth(tmp_path: Path) -> AuthManager:
    a = AuthManager(str(tmp_path))
    return a


@pytest.fixture()
def api(auth: AuthManager, cache: APICache) -> YouTubeMusicAPI:
    a = YouTubeMusicAPI(auth, cache)
    # Inject a mock ytmuxiris instance
    mock_yt = MagicMock()
    a._ytmuxiris = mock_yt
    return a


class TestSearch:
    async def test_search_returns_songs(self, api: YouTubeMusicAPI) -> None:
        raw = [
            {
                "videoId": "abc123",
                "title": "Test Song",
                "artists": [{"name": "Artist One"}],
                "duration": "3:45",
                "thumbnails": [{"url": "http://thumb.jpg"}],
            }
        ]
        api._ytmuxiris.search = MagicMock(return_value=raw)

        songs = await api.search_songs("test")

        assert len(songs) == 1
        assert songs[0].video_id == "abc123"
        assert songs[0].title == "Test Song"
        assert songs[0].artist == "Artist One"
        assert songs[0].duration == 225

    async def test_search_empty_on_exception(self, api: YouTubeMusicAPI) -> None:
        api._ytmuxiris.search = MagicMock(side_effect=Exception("network error"))
        songs = await api.search_songs("test")
        assert songs == []

    async def test_search_cached(self, api: YouTubeMusicAPI, cache: APICache) -> None:
        raw = [{"videoId": "x1", "title": "Cached", "artists": [{"name": "A"}], "duration": "1:00"}]
        api._ytmuxiris.search = MagicMock(return_value=raw)

        await api.search_songs("query")
        await api.search_songs("query")  # second call should hit cache

        assert api._ytmuxiris.search.call_count == 1


class TestLibrary:
    async def test_get_library_songs(self, api: YouTubeMusicAPI) -> None:
        api._ytmuxiris.get_library_songs = MagicMock(
            return_value=[
                {
                    "videoId": "s1",
                    "title": "Lib Song",
                    "artists": [{"name": "B"}],
                    "duration": "2:00",
                }
            ]
        )
        songs = await api.get_library_songs()
        assert len(songs) == 1
        assert songs[0].title == "Lib Song"

    async def test_like_song(self, api: YouTubeMusicAPI) -> None:
        api._ytmuxiris.rate_song = MagicMock(return_value=None)
        result = await api.like_song("vid1")
        assert result is True
        api._ytmuxiris.rate_song.assert_called_once_with("vid1", "LIKE")

    async def test_like_song_failure(self, api: YouTubeMusicAPI) -> None:
        api._ytmuxiris.rate_song = MagicMock(side_effect=Exception("fail"))
        result = await api.like_song("vid1")
        assert result is False


class TestParsing:
    def test_parse_song_basic(self, api: YouTubeMusicAPI) -> None:
        data = {
            "videoId": "v1",
            "title": "My Song",
            "artists": [{"name": "Artist"}, {"name": "Featured"}],
            "album": {"name": "My Album"},
            "duration": "4:20",
            "thumbnails": [{"url": "low.jpg"}, {"url": "high.jpg"}],
        }
        song = api._parse_song(data)
        assert song.video_id == "v1"
        assert song.title == "My Song"
        assert "Artist" in song.artist
        assert song.album == "My Album"
        assert song.duration == 260
        assert song.thumbnail == "high.jpg"

    def test_parse_song_missing_fields(self, api: YouTubeMusicAPI) -> None:
        song = api._parse_song({})
        assert song.video_id == ""
        assert song.title == "Unknown"
        assert song.duration == 0
