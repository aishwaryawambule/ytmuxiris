from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label

from ytmuxiris.models import Playlist
from ytmuxiris.ui.widgets.loading_spinner import LoadingSpinner
from ytmuxiris.ui.widgets.song_list import SongList


class PlaylistScreen(Screen):
    """Shows all tracks in a single playlist."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("p", "play_all", "Play all"),
        ("delete", "delete_playlist", "Delete playlist"),
    ]

    def __init__(self, playlist_id: str) -> None:
        super().__init__()
        self._playlist_id = playlist_id
        self._playlist: Playlist | None = None
        # YouTube Music system playlists (Liked Music, Saved Episodes, etc.)
        # can't be deleted, and individual tracks must be unliked rather than
        # removed via the playlist API.
        self._is_system = playlist_id in {"LM", "SE", "HISTORY"} or not playlist_id.startswith("PL")

    def compose(self) -> ComposeResult:
        with Horizontal(id="playlist-header"):
            yield Label("◉", classes="playlist-art")
            with Vertical(id="playlist-meta"):
                yield Label("Loading…", classes="playlist-title", id="pl-title")
                yield Label("", classes="playlist-description", id="pl-desc")
                yield Label("", classes="playlist-count", id="pl-count")
            yield Button("▶ Play all", id="btn-play-all")
            if not self._is_system:
                yield Button("🗑 Delete", id="btn-delete-pl", classes="danger")
        yield LoadingSpinner("Loading playlist…", id="pl-spinner")
        yield SongList(id="pl-song-list", show_remove=not self._is_system)

    def on_mount(self) -> None:
        self.query_one("#pl-song-list").display = False
        self.load_playlist()

    @work(exclusive=True)
    async def load_playlist(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        pl = await api.get_playlist(self._playlist_id)
        self.query_one("#pl-spinner").display = False

        if pl is None:
            self.query_one("#pl-title", Label).update("Failed to load playlist")
            return

        self._playlist = pl
        self.query_one("#pl-title", Label).update(pl.title)
        self.query_one("#pl-desc", Label).update(pl.description)
        self.query_one("#pl-count", Label).update(f"{pl.track_count} tracks")

        song_list = self.query_one("#pl-song-list", SongList)
        song_list.set_songs(pl.tracks)
        song_list.display = True

    def on_song_list_song_selected(self, event: SongList.SongSelected) -> None:
        tracks = self._playlist.tracks if self._playlist else event.songs
        try:
            idx = next(i for i, s in enumerate(tracks) if s.video_id == event.song.video_id)
        except StopIteration:
            idx = 0
        self.run_worker(
            self.app.queue.play_from(tracks, idx),  # type: ignore[attr-defined]
            exclusive=False,
        )
        event.stop()

    def on_song_row_remove_from_playlist(self, event) -> None:  # type: ignore[no-untyped-def]
        self._remove_song(event.song.video_id, event.song.title)
        event.stop()

    @work(exclusive=False)
    async def _remove_song(self, video_id: str, title: str) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        ok = await api.remove_from_playlist(self._playlist_id, [video_id])
        if not ok:
            try:
                self.app.notify(f"Failed to remove “{title}”", timeout=3)  # type: ignore[attr-defined]
            except Exception:
                pass
            return
        if self._playlist is not None:
            self._playlist.tracks = [s for s in self._playlist.tracks if s.video_id != video_id]
            self._playlist.track_count = len(self._playlist.tracks)
            self.query_one("#pl-count", Label).update(f"{self._playlist.track_count} tracks")
            self.query_one("#pl-song-list", SongList).set_songs(self._playlist.tracks)
        try:
            self.app.notify(f"Removed “{title}” from playlist", timeout=2)  # type: ignore[attr-defined]
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-play-all":
            self.action_play_all()
        elif event.button.id == "btn-delete-pl":
            self.action_delete_playlist()
        event.stop()

    def action_play_all(self) -> None:
        if self._playlist and self._playlist.tracks:
            self.app.queue.set_queue(self._playlist.tracks)  # type: ignore[attr-defined]
            self.run_worker(
                self.app.queue.play_now(self._playlist.tracks[0]),  # type: ignore[attr-defined]
                exclusive=False,
            )

    def action_delete_playlist(self) -> None:
        if self._is_system:
            try:
                self.app.notify("System playlists can't be deleted", timeout=2)  # type: ignore[attr-defined]
            except Exception:
                pass
            return
        from ytmuxiris.ui.screens.confirm import ConfirmScreen

        title = self._playlist.title if self._playlist else "this playlist"

        def _after(confirmed: bool | None) -> None:
            if confirmed:
                self._delete_playlist()

        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmScreen(
                f"Delete playlist “{title}”?",
                "This cannot be undone.",
            ),
            _after,
        )

    @work(exclusive=True)
    async def _delete_playlist(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        ok = await api.delete_playlist(self._playlist_id)
        if not ok:
            try:
                self.app.notify("Failed to delete playlist", timeout=3)  # type: ignore[attr-defined]
            except Exception:
                pass
            return
        try:
            self.app._cache.invalidate_library()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.app.notify("Playlist deleted", timeout=2)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.app.pop_screen()  # type: ignore[attr-defined]
