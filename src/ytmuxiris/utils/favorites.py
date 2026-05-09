from __future__ import annotations

import json
from pathlib import Path

from textual.message import Message

from ytmuxiris.models.models import Song
from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)


class FavoritesStore:
    """JSON-backed store of liked songs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._songs: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text())
                if isinstance(raw, list):
                    self._songs = {
                        d["video_id"]: d for d in raw if isinstance(d, dict) and d.get("video_id")
                    }
        except Exception as e:
            logger.warning("Failed to load favorites: %s", e)
            self._songs = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(list(self._songs.values()), indent=2))
        except Exception as e:
            logger.error("Failed to save favorites: %s", e)

    def is_liked(self, video_id: str | None) -> bool:
        return bool(video_id) and video_id in self._songs

    def add(self, song: Song) -> None:
        if not song.video_id:
            return
        self._songs[song.video_id] = {
            "video_id": song.video_id,
            "title": song.title,
            "artist": song.artist,
            "album": song.album,
            "duration": song.duration,
            "thumbnail": song.thumbnail,
        }
        self._save()

    def remove(self, video_id: str) -> None:
        if video_id in self._songs:
            self._songs.pop(video_id, None)
            self._save()

    def list(self) -> list[Song]:
        return [
            Song(
                video_id=d.get("video_id", ""),
                title=d.get("title", "Unknown"),
                artist=d.get("artist", ""),
                album=d.get("album"),
                duration=int(d.get("duration") or 0),
                thumbnail=d.get("thumbnail"),
                liked=True,
            )
            for d in self._songs.values()
        ]


class FavoritesChanged(Message):
    """Posted on the app after a song's favorite state changes."""

    def __init__(self, song: Song, liked: bool) -> None:
        super().__init__()
        self.song = song
        self.liked = liked
