from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from ytmuxiris.ui.widgets.song_list import SongList


class FavoritesView(Widget):
    """List of locally-favorited songs."""

    BINDINGS = [
        ("/", "focus_search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="fav-header"):
            yield Label("Favorites", classes="screen-title")
        with Vertical(id="fav-body"):
            yield Static(
                "No favorites yet — tap ♡ on any song to add it.",
                id="fav-empty",
                classes="text-muted",
            )
            yield SongList(id="fav-song-list")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        store = self.app.favorites  # type: ignore[attr-defined]
        songs = store.list()
        sl = self.query_one("#fav-song-list", SongList)
        sl.set_songs(songs)
        empty = self.query_one("#fav-empty", Static)
        empty.display = not songs
        sl.display = bool(songs)

    def on_song_list_song_selected(self, event: SongList.SongSelected) -> None:
        self.run_worker(
            self.app.queue.play_from(event.songs, event.index),  # type: ignore[attr-defined]
            exclusive=False,
        )
        event.stop()

    def action_focus_search(self) -> None:
        self.app.show_view("search")  # type: ignore[attr-defined]
