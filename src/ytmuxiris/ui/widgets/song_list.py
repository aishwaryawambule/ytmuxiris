from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label

from ytmuxiris.utils.helpers import format_duration

if TYPE_CHECKING:
    from ytmuxiris.models import Song


class SongRow(Widget):
    """One row in the song list."""

    liked: reactive[bool] = reactive(False)
    playing: reactive[bool] = reactive(False)
    duration: reactive[int] = reactive(0)

    class Selected(Message):
        def __init__(self, song: Song) -> None:
            super().__init__()
            self.song = song

    class LikeToggled(Message):
        def __init__(self, song: Song, liked: bool) -> None:
            super().__init__()
            self.song = song
            self.liked = liked

    class AddToQueue(Message):
        def __init__(self, song: Song) -> None:
            super().__init__()
            self.song = song

    class AddToPlaylist(Message):
        def __init__(self, song: Song) -> None:
            super().__init__()
            self.song = song

    class RemoveFromPlaylist(Message):
        def __init__(self, song: Song) -> None:
            super().__init__()
            self.song = song

    def __init__(self, song: Song, index: int, *, show_remove: bool = False) -> None:
        super().__init__(classes="song-row")
        self.song = song
        self.index = index
        self.liked = song.liked
        self.duration = song.duration
        self._show_remove = show_remove

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(str(self.index), classes="track-num")
            with Vertical(classes="song-info"):
                yield Label(self.song.title, classes="song-title", id=f"title-{self.index}")
                yield Label(self.song.artist, classes="song-artist")
            album = self.song.album or ""
            if album.strip().lower() == self.song.title.strip().lower():
                album = ""
            yield Label(album, classes="song-album")
            yield Label(
                format_duration(self.song.duration),
                classes="song-duration",
                id=f"dur-{self.index}",
            )
            yield Button(
                "+",
                id=f"queue-{self.index}",
                classes="queue-btn",
            )
            yield Button(
                "≡",
                id=f"addpl-{self.index}",
                classes="addpl-btn",
            )
            yield Button(
                "♥" if self.liked else "♡",
                id=f"like-{self.index}",
                classes="like-btn",
            )
            if self._show_remove:
                yield Button(
                    "✕",
                    id=f"rm-{self.index}",
                    classes="remove-btn",
                )

    def watch_liked(self, liked: bool) -> None:
        try:
            btn = self.query_one(f"#like-{self.index}", Button)
            btn.label = "♥" if liked else "♡"
            if liked:
                btn.add_class("liked")
            else:
                btn.remove_class("liked")
        except Exception:
            return

    def watch_playing(self, playing: bool) -> None:
        if playing:
            self.add_class("playing")
        else:
            self.remove_class("playing")
        try:
            num_lbl = self.query_one(".track-num", Label)
            num_lbl.update("♫" if playing else str(self.index))
        except Exception:
            return

    def watch_duration(self, duration: int) -> None:
        try:
            lbl = self.query_one(f"#dur-{self.index}", Label)
            lbl.update(format_duration(duration))
        except Exception:
            return

    def on_click(self, event: events.Click) -> None:
        # Click events bubble up from children. If the click landed on one of
        # our action buttons (+ / ♥), don't treat it as "play this song" —
        # let on_button_pressed handle it instead.
        target = getattr(event, "widget", None)
        node = target
        while node is not None and node is not self:
            if isinstance(node, Button):
                return
            node = getattr(node, "parent", None)
        self.post_message(self.Selected(self.song))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("like-"):
            self.liked = not self.liked
            self.post_message(self.LikeToggled(self.song, self.liked))
            event.stop()
        elif bid.startswith("queue-"):
            self.post_message(self.AddToQueue(self.song))
            event.stop()
        elif bid.startswith("addpl-"):
            self.post_message(self.AddToPlaylist(self.song))
            event.stop()
        elif bid.startswith("rm-"):
            self.post_message(self.RemoveFromPlaylist(self.song))
            event.stop()


class SongList(Widget):
    """Scrollable list of SongRow widgets."""

    class SongSelected(Message):
        def __init__(
            self,
            song: Song,
            songs: list[Song] | None = None,
            index: int | None = None,
        ) -> None:
            super().__init__()
            self.song = song
            # Full section list + clicked index, so handlers can queue the
            # whole section and let auto-advance walk through it.
            self.songs: list[Song] = list(songs) if songs is not None else [song]
            self.index: int = index if index is not None else 0

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
        show_remove: bool = False,
    ) -> None:
        widget_classes = "song-list"
        if classes:
            widget_classes = f"{widget_classes} {classes}"
        super().__init__(name=name, id=id, classes=widget_classes, disabled=disabled)
        self._songs: list[Song] = []
        self._current_video_id: str | None = None
        self._show_remove = show_remove

    def compose(self) -> ComposeResult:
        return iter([])

    def set_songs(self, songs: list[Song]) -> None:
        fav = getattr(self.app, "favorites", None)
        if fav is not None:
            for s in songs:
                if fav.is_liked(s.video_id):
                    s.liked = True
        self._songs = songs
        self._rebuild()

    def refresh_liked_state(self, video_id: str, liked: bool) -> None:
        for s in self._songs:
            if s.video_id == video_id:
                s.liked = liked
        for row in self.query(SongRow):
            if row.song.video_id == video_id:
                row.song.liked = liked
                row.liked = liked

    def set_playing(self, video_id: str | None) -> None:
        self._current_video_id = video_id
        for row in self.query(SongRow):
            row.playing = row.song.video_id == video_id

    def _rebuild(self) -> None:
        self.remove_children()
        for i, song in enumerate(self._songs, start=1):
            row = SongRow(song, i, show_remove=self._show_remove)
            row.playing = song.video_id == self._current_video_id
            self.mount(row)
        # Some endpoints (home shelves, watch playlists) don't include
        # durations — backfill them in the background so the row stops
        # showing 0:00.
        self._hydrate_durations()

    def _hydrate_durations(self) -> None:
        missing = [s for s in self._songs if s.duration <= 0 and s.video_id]
        if not missing:
            return
        try:
            asyncio.create_task(self._backfill_durations(list(missing)))
        except RuntimeError:
            return

    async def _backfill_durations(self, songs: list[Song]) -> None:
        api = getattr(self.app, "api", None)
        if api is None:
            return
        sem = asyncio.Semaphore(4)

        async def _one(s: Song) -> None:
            async with sem:
                secs = await api.get_song_duration(s.video_id)
            if secs <= 0:
                return
            s.duration = secs
            try:
                for row in self.query(SongRow):
                    if row.song.video_id == s.video_id:
                        row.duration = secs
                        break
            except Exception:
                pass

        await asyncio.gather(*(_one(s) for s in songs), return_exceptions=True)

    def on_song_row_selected(self, event: SongRow.Selected) -> None:
        try:
            idx = next(i for i, s in enumerate(self._songs) if s.video_id == event.song.video_id)
        except StopIteration:
            idx = 0
        self.post_message(self.SongSelected(event.song, self._songs, idx))
        event.stop()

    def on_song_row_like_toggled(self, event: SongRow.LikeToggled) -> None:
        asyncio.create_task(self._handle_like(event.song, event.liked))
        event.stop()

    def on_song_row_add_to_queue(self, event: SongRow.AddToQueue) -> None:
        try:
            self.app.queue.add(event.song)  # type: ignore[attr-defined]
            self.app.notify(  # type: ignore[attr-defined]
                f"Added “{event.song.title}” to queue",
                timeout=2,
            )
        except Exception:
            pass
        event.stop()

    async def _handle_like(self, song: Song, liked: bool) -> None:
        from ytmuxiris.utils.favorites import FavoritesChanged

        app = self.app  # type: ignore[attr-defined]
        fav = getattr(app, "favorites", None)
        if fav is not None:
            if liked:
                fav.add(song)
            else:
                fav.remove(song.video_id)
        song.liked = liked
        app.post_message(FavoritesChanged(song, liked))
        api = app.api
        try:
            if liked:
                await api.like_song(song.video_id)
            else:
                await api.unlike_song(song.video_id)
        except Exception:
            pass
