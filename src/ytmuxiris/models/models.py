from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Song:
    video_id: str
    title: str
    artist: str
    album: str | None = None
    duration: int = 0  # seconds
    thumbnail: str | None = None
    liked: bool = False
    lyrics_browse_id: str | None = None

    def __hash__(self) -> int:
        return hash(self.video_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Song):
            return NotImplemented
        return self.video_id == other.video_id


@dataclass
class Album:
    browse_id: str
    title: str
    artist: str
    year: str | None = None
    thumbnail: str | None = None
    tracks: list[Song] = field(default_factory=list)
    track_count: int = 0


@dataclass
class Artist:
    channel_id: str
    name: str
    thumbnail: str | None = None
    subscriber_count: str | None = None
    top_songs: list[Song] = field(default_factory=list)
    albums: list[Album] = field(default_factory=list)
    subscribed: bool = False


@dataclass
class Playlist:
    playlist_id: str
    title: str
    description: str = ""
    thumbnail: str | None = None
    track_count: int = 0
    tracks: list[Song] = field(default_factory=list)
    author: str | None = None
    privacy: str = "PRIVATE"
