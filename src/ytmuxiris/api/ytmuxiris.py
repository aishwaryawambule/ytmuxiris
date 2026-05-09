from __future__ import annotations

import asyncio
from asyncio import Semaphore
from typing import Any

from ytmuxiris.api.auth import AuthManager
from ytmuxiris.models import Album, Artist, Playlist, Song
from ytmuxiris.utils.cache import (
    TTL_ALBUM,
    TTL_ARTIST,
    TTL_LIBRARY,
    TTL_SEARCH,
    APICache,
)
from ytmuxiris.utils.helpers import parse_duration
from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)


class YouTubeMusicAPI:
    """Async wrapper around ytmuxirisapi with caching and rate limiting."""

    def __init__(self, auth: AuthManager, cache: APICache) -> None:
        self._auth = auth
        self._cache = cache
        self._ytmuxiris: Any = None
        self._semaphore = Semaphore(5)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Load ytmuxirisapi instance from saved credentials."""
        instance = await asyncio.to_thread(self._auth.get_ytmuxiris)
        if instance is None:
            return False
        self._ytmuxiris = instance
        logger.info("Authenticated with YouTube Music")
        return True

    def is_authenticated(self) -> bool:
        return self._ytmuxiris is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Rate-limited async call to a synchronous ytmuxirisapi method."""
        async with self._semaphore:
            return await asyncio.to_thread(fn, *args, **kwargs)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        filter: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        key = self._cache.make_key("search", q=query, f=filter, limit=limit)
        cached = self._cache.get(key, TTL_SEARCH)
        if cached is not None:
            return cached  # type: ignore[return-value]
        try:
            results = await self._call(self._ytmuxiris.search, query, filter=filter, limit=limit)
            self._cache.set(key, results)
            return results or []
        except Exception as e:
            logger.error("Search failed: %s", e)
            return []

    async def search_songs(self, query: str, limit: int = 20) -> list[Song]:
        results = await self.search(query, filter="songs", limit=limit)
        return [self._parse_song(r) for r in results]

    async def search_albums(self, query: str, limit: int = 20) -> list[Album]:
        results = await self.search(query, filter="albums", limit=limit)
        return [self._parse_album(r) for r in results]

    async def search_artists(self, query: str, limit: int = 20) -> list[Artist]:
        results = await self.search(query, filter="artists", limit=limit)
        return [self._parse_artist(r) for r in results]

    async def search_playlists(self, query: str, limit: int = 20) -> list[Playlist]:
        results = await self.search(query, filter="playlists", limit=limit)
        return [self._parse_playlist(r) for r in results]

    async def get_search_suggestions(self, query: str) -> list[str]:
        try:
            return await self._call(self._ytmuxiris.get_search_suggestions, query) or []
        except Exception as e:
            logger.error("Suggestions failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------

    async def get_library_songs(self, limit: int = 100) -> list[Song]:
        key = self._cache.make_key("library_songs", limit=limit)
        cached = self._cache.get(key, TTL_LIBRARY)
        if cached is not None:
            return [self._parse_song(s) for s in cached]
        try:
            data = await self._call(self._ytmuxiris.get_library_songs, limit=limit)
            self._cache.set(key, data or [])
            return [self._parse_song(s) for s in (data or [])]
        except Exception as e:
            logger.error("get_library_songs failed: %s", e)
            return []

    async def get_library_albums(self, limit: int = 100) -> list[Album]:
        key = self._cache.make_key("library_albums", limit=limit)
        cached = self._cache.get(key, TTL_LIBRARY)
        if cached is not None:
            return [self._parse_album(a) for a in cached]
        try:
            data = await self._call(self._ytmuxiris.get_library_albums, limit=limit)
            self._cache.set(key, data or [])
            return [self._parse_album(a) for a in (data or [])]
        except Exception as e:
            logger.error("get_library_albums failed: %s", e)
            return []

    async def get_library_artists(self, limit: int = 100) -> list[Artist]:
        key = self._cache.make_key("library_artists", limit=limit)
        cached = self._cache.get(key, TTL_LIBRARY)
        if cached is not None:
            return [self._parse_artist(a) for a in cached]
        try:
            data = await self._call(self._ytmuxiris.get_library_artists, limit=limit)
            self._cache.set(key, data or [])
            return [self._parse_artist(a) for a in (data or [])]
        except Exception as e:
            logger.error("get_library_artists failed: %s", e)
            return []

    async def get_library_playlists(self, limit: int = 100) -> list[Playlist]:
        key = self._cache.make_key("library_playlists", limit=limit)
        cached = self._cache.get(key, TTL_LIBRARY)
        if cached is not None:
            return [self._parse_playlist(p) for p in cached]
        try:
            data = await self._call(self._ytmuxiris.get_library_playlists, limit=limit)
            self._cache.set(key, data or [])
            return [self._parse_playlist(p) for p in (data or [])]
        except Exception as e:
            logger.error("get_library_playlists failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Ratings
    # ------------------------------------------------------------------

    async def like_song(self, video_id: str) -> bool:
        try:
            await self._call(self._ytmuxiris.rate_song, video_id, "LIKE")
            self._cache.invalidate_library()
            return True
        except Exception as e:
            logger.error("like_song failed: %s", e)
            return False

    async def unlike_song(self, video_id: str) -> bool:
        try:
            await self._call(self._ytmuxiris.rate_song, video_id, "INDIFFERENT")
            self._cache.invalidate_library()
            return True
        except Exception as e:
            logger.error("unlike_song failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    async def get_playlist(self, playlist_id: str) -> Playlist | None:
        key = self._cache.make_key("playlist", id=playlist_id)
        cached = self._cache.get(key, TTL_LIBRARY)
        if cached is not None:
            return self._parse_playlist_full(cached)
        try:
            data = await self._call(self._ytmuxiris.get_playlist, playlist_id, limit=None)
            if data:
                self._cache.set(key, data)
            return self._parse_playlist_full(data) if data else None
        except Exception as e:
            logger.error("get_playlist failed: %s", e)
            return None

    async def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "PRIVATE",
    ) -> str | None:
        try:
            pid = await self._call(
                self._ytmuxiris.create_playlist,
                title=title,
                description=description,
                privacy_status=privacy_status,
            )
            self._cache.invalidate_library()
            return pid
        except Exception as e:
            logger.error("create_playlist failed: %s", e)
            return None

    async def delete_playlist(self, playlist_id: str) -> bool:
        try:
            await self._call(self._ytmuxiris.delete_playlist, playlist_id)
            self._cache.invalidate_library()
            return True
        except Exception as e:
            logger.error("delete_playlist failed: %s", e)
            return False

    async def add_to_playlist(self, playlist_id: str, video_ids: list[str]) -> bool:
        try:
            await self._call(
                self._ytmuxiris.add_playlist_items,
                playlistId=playlist_id,
                videoIds=video_ids,
            )
            self._cache.invalidate(self._cache.make_key("playlist", id=playlist_id))
            return True
        except Exception as e:
            logger.error("add_to_playlist failed: %s", e)
            return False

    async def remove_from_playlist(self, playlist_id: str, video_ids: list[str]) -> bool:
        try:
            data = await self._call(self._ytmuxiris.get_playlist, playlist_id)
            tracks_to_remove = [
                {"videoId": t["videoId"], "setVideoId": t["setVideoId"]}
                for t in (data.get("tracks") or [])
                if t.get("videoId") in video_ids
            ]
            if tracks_to_remove:
                await self._call(
                    self._ytmuxiris.remove_playlist_items,
                    playlist_id,
                    tracks_to_remove,
                )
            self._cache.invalidate(self._cache.make_key("playlist", id=playlist_id))
            return True
        except Exception as e:
            logger.error("remove_from_playlist failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Artist / Album detail
    # ------------------------------------------------------------------

    async def get_artist(self, channel_id: str) -> Artist | None:
        key = self._cache.make_key("artist", id=channel_id)
        cached = self._cache.get(key, TTL_ARTIST)
        if cached is not None:
            return self._parse_artist_full(cached)
        try:
            data = await self._call(self._ytmuxiris.get_artist, channel_id)
            if data:
                self._cache.set(key, data)
            return self._parse_artist_full(data) if data else None
        except Exception as e:
            logger.error("get_artist failed: %s", e)
            return None

    async def get_album(self, browse_id: str) -> Album | None:
        key = self._cache.make_key("album", id=browse_id)
        cached = self._cache.get(key, TTL_ALBUM)
        if cached is not None:
            return self._parse_album_full(cached)
        try:
            data = await self._call(self._ytmuxiris.get_album, browse_id)
            if data:
                self._cache.set(key, data)
            return self._parse_album_full(data) if data else None
        except Exception as e:
            logger.error("get_album failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Recommendations & Radio
    # ------------------------------------------------------------------

    async def get_home_feed(self) -> list[dict[str, Any]]:
        """Return the list of home shelves. Each shelf has 'title' and 'contents'."""
        key = self._cache.make_key("home_feed")
        cached = self._cache.get(key, TTL_SEARCH)
        if cached is not None:
            return cached  # type: ignore[return-value]
        try:
            data = await self._call(self._ytmuxiris.get_home, limit=20)
            if data:
                self._cache.set(key, data)
            return data or []
        except Exception as e:
            logger.error("get_home_feed failed: %s", e)
            return []

    async def get_similar_songs(self, video_id: str) -> list[Song]:
        try:
            data = await self._call(self._ytmuxiris.get_watch_playlist, video_id)
            tracks = (data or {}).get("tracks", [])
            return [self._parse_song(t) for t in tracks[1:]]
        except Exception as e:
            logger.error("get_similar_songs failed: %s", e)
            return []

    async def get_song_radio(self, video_id: str) -> list[Song]:
        try:
            data = await self._call(self._ytmuxiris.get_watch_playlist, video_id, radio=True)
            tracks = (data or {}).get("tracks", [])
            return [self._parse_song(t) for t in tracks]
        except Exception as e:
            logger.error("get_song_radio failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def get_stream_url(self, video_id: str, quality: str = "high") -> str | None:
        # MPV is configured with ytdl_hook + the standalone yt-dlp binary, which
        # handles YouTube format selection and HLS variant resolution correctly.
        # We just hand it the watch URL; trying to pre-resolve to a media URL
        # ourselves yields HLS master playlists that MPV mis-detects as 29-entry
        # nested playlists (every entry then "loading failed").
        return f"https://music.youtube.com/watch?v={video_id}"

    # Browsers we'll try in order when passing cookies to yt-dlp.
    _COOKIE_BROWSERS = (
        "brave",
        "chrome",
        "chromium",
        "firefox",
        "edge",
        "opera",
        "vivaldi",
        "safari",
    )

    # Player-client strategies, in order of preference. The default player
    # clients reject most music tracks ("Requested format is not available")
    # because YouTube now gates DASH streams behind a PO token. The web_safari
    # client still serves combined HLS streams that MPV can play.
    _CLIENT_STRATEGIES = (
        ("web_safari",),
        ("ios",),
        ("android",),
        ("web",),
    )

    async def _stream_via_ytdlp(self, video_id: str) -> str | None:
        try:
            import yt_dlp
        except Exception as e:
            logger.error("yt-dlp not available: %s", e)
            return None

        yt_urls = (
            f"https://music.youtube.com/watch?v={video_id}",
            f"https://www.youtube.com/watch?v={video_id}",
        )

        def _pick_url(info: dict) -> str | None:
            if not info:
                return None
            if info.get("url"):
                return info["url"]
            formats = info.get("formats") or []
            # Prefer audio-only; otherwise any playable stream.
            audio_only = [
                f
                for f in formats
                if f.get("vcodec") in (None, "none")
                and f.get("acodec") not in (None, "none")
                and f.get("url")
            ]
            playable = audio_only or [
                f for f in formats if f.get("url") and f.get("acodec") not in (None, "none")
            ]
            if not playable:
                return None
            playable.sort(
                key=lambda f: (f.get("abr") or f.get("tbr") or 0),
                reverse=True,
            )
            return playable[0].get("url")

        def _try(url: str, *, client: tuple[str, ...] | None, browser: str | None) -> str | None:
            opts: dict[str, Any] = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
            }
            if client:
                opts["extractor_args"] = {"youtube": {"player_client": list(client)}}
            if browser:
                opts["cookiesfrombrowser"] = (browser,)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                return _pick_url(info or {})
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "yt-dlp try failed (client=%s browser=%s url=%s): %s",
                    client,
                    browser,
                    url,
                    str(exc)[:120],
                )
                return None

        def _extract() -> str | None:
            # 1. Best path: matching browser cookies + safari client (HLS).
            for browser in self._COOKIE_BROWSERS:
                for client in self._CLIENT_STRATEGIES:
                    for url in yt_urls:
                        result = _try(url, client=client, browser=browser)
                        if result:
                            return result
            # 2. No cookies — last resort, may work for non-restricted tracks.
            for client in self._CLIENT_STRATEGIES:
                for url in yt_urls:
                    result = _try(url, client=client, browser=None)
                    if result:
                        return result
            return None

        try:
            return await asyncio.to_thread(_extract)
        except Exception as e:
            logger.error("yt-dlp stream extraction failed for %s: %s", video_id, e)
            return None

    async def get_song_duration(self, video_id: str) -> int:
        """Resolve a song's length in seconds.

        Used to backfill durations for items that come from endpoints (home
        feed shelves, watch playlists) which don't include them. Result is
        cached aggressively since a song's length never changes.
        """
        if not video_id:
            return 0
        key = self._cache.make_key("song_duration", id=video_id)
        cached = self._cache.get(key, TTL_LIBRARY)
        if cached is not None:
            try:
                return int(cached)
            except (TypeError, ValueError):
                pass
        try:
            data = await self._call(self._ytmuxiris.get_song, video_id)
            details = (data or {}).get("videoDetails") or {}
            secs = parse_duration(details.get("lengthSeconds") or details.get("durationMs") or 0)
            # durationMs is in milliseconds — convert if it looks like one.
            ms = details.get("durationMs")
            if ms and not details.get("lengthSeconds"):
                try:
                    secs = int(int(ms) / 1000)
                except (TypeError, ValueError):
                    pass
            self._cache.set(key, secs)
            return secs
        except Exception as e:
            logger.debug("get_song_duration(%s) failed: %s", video_id, e)
            return 0

    async def get_lyrics(self, video_id: str) -> str | None:
        try:
            watch = await self._call(self._ytmuxiris.get_watch_playlist, video_id)
            lyrics_id = (watch or {}).get("lyrics")
            if lyrics_id:
                lyrics = await self._call(self._ytmuxiris.get_lyrics, lyrics_id)
                return (lyrics or {}).get("lyrics")
        except Exception as e:
            logger.error("get_lyrics failed: %s", e)
        return None

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_song(self, data: dict[str, Any] | None) -> Song:
        # ytmusicapi returns duration in different fields depending on the
        # endpoint: "duration" ("3:45") for search/library, "duration_seconds"
        # (225) for watch-playlist/queue, "lengthSeconds" ("225") for some
        # raw player payloads. Fall through them so the UI never shows 0:00
        # for a song that actually has a known length.
        if not isinstance(data, dict):
            return Song(
                video_id="",
                title="Unknown",
                artist="Unknown Artist",
                album=None,
                duration=0,
                thumbnail=None,
            )
        dur = data.get("duration_seconds") or data.get("lengthSeconds") or data.get("duration") or 0
        return Song(
            video_id=data.get("videoId") or "",
            title=data.get("title") or "Unknown",
            artist=self._extract_artists(data),
            album=self._extract_album_name(data),
            duration=parse_duration(dur),
            thumbnail=self._best_thumbnail(data),
        )

    def _parse_album(self, data: dict[str, Any]) -> Album:
        artists = [a for a in (data.get("artists") or []) if isinstance(a, dict)]
        artist_name = ", ".join(a.get("name", "") for a in artists) if artists else "Unknown"
        return Album(
            browse_id=data.get("browseId") or "",
            title=data.get("title") or "Unknown",
            artist=artist_name,
            year=data.get("year"),
            thumbnail=self._best_thumbnail(data),
            track_count=data.get("trackCount") or 0,
        )

    def _parse_artist(self, data: dict[str, Any]) -> Artist:
        return Artist(
            channel_id=data.get("browseId") or "",
            name=data.get("artist") or data.get("name") or "Unknown",
            thumbnail=self._best_thumbnail(data),
            subscriber_count=data.get("subscribers"),
        )

    def _parse_playlist(self, data: dict[str, Any]) -> Playlist:
        return Playlist(
            playlist_id=data.get("playlistId") or data.get("browseId") or "",
            title=data.get("title") or "Unknown",
            description=data.get("description") or "",
            thumbnail=self._best_thumbnail(data),
            track_count=data.get("count") or 0,
        )

    def _parse_playlist_full(self, data: dict[str, Any]) -> Playlist:
        pl = self._parse_playlist(data)
        raw_tracks = data.get("tracks") or []
        pl.tracks = [self._parse_song(t) for t in raw_tracks]
        pl.track_count = len(pl.tracks)
        return pl

    def _parse_album_full(self, data: dict[str, Any]) -> Album:
        album = self._parse_album(data)
        raw_tracks = data.get("tracks") or []
        album.tracks = [self._parse_song(t) for t in raw_tracks]
        album.track_count = len(album.tracks)
        return album

    def _parse_artist_full(self, data: dict[str, Any]) -> Artist:
        artist = self._parse_artist(data)
        songs_section = (data.get("songs") or {}).get("results") or []
        artist.top_songs = [self._parse_song(s) for s in songs_section]
        return artist

    def _extract_artists(self, data: dict[str, Any]) -> str:
        artists = [a for a in (data.get("artists") or []) if isinstance(a, dict)]
        if artists:
            return ", ".join(a.get("name", "") for a in artists)
        return data.get("author") or "Unknown Artist"

    def _extract_album_name(self, data: dict[str, Any]) -> str | None:
        album = data.get("album")
        if isinstance(album, dict):
            return album.get("name")
        return album

    @staticmethod
    def _best_thumbnail(data: dict[str, Any]) -> str | None:
        thumbnails = data.get("thumbnails") or []
        if thumbnails:
            return thumbnails[-1].get("url")
        return None
