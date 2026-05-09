from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

if TYPE_CHECKING:
    from ytmuxiris.models import Playlist


class PlaylistCard(Widget):
    """Card widget for a single playlist."""

    class Selected(Message):
        def __init__(self, playlist: Playlist) -> None:
            super().__init__()
            self.playlist = playlist

    def __init__(self, playlist: Playlist) -> None:
        super().__init__(classes="playlist-card")
        self.playlist = playlist

    def compose(self) -> ComposeResult:
        yield Label("♫", classes="playlist-art-placeholder")
        yield Label(self.playlist.title, classes="playlist-card-title")
        if self.playlist.description:
            yield Label(self.playlist.description, classes="playlist-card-desc")
        yield Label(
            f"{self.playlist.track_count} tracks" if self.playlist.track_count else "",
            classes="playlist-card-count",
        )

    def on_click(self) -> None:
        self.post_message(self.Selected(self.playlist))


class PlaylistGrid(Widget):
    """Grid of PlaylistCard widgets."""

    class PlaylistSelected(Message):
        def __init__(self, playlist: Playlist) -> None:
            super().__init__()
            self.playlist = playlist

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        widget_classes = "playlist-grid"
        if classes:
            widget_classes = f"{widget_classes} {classes}"
        super().__init__(name=name, id=id, classes=widget_classes, disabled=disabled)
        self._playlists: list[Playlist] = []

    def compose(self) -> ComposeResult:
        return iter([])

    def set_playlists(self, playlists: list[Playlist]) -> None:
        self._playlists = playlists
        self.remove_children()
        if not playlists:
            self.mount(Label("No playlists found", classes="text-muted"))
            return
        for pl in playlists:
            self.mount(PlaylistCard(pl))

    def on_playlist_card_selected(self, event: PlaylistCard.Selected) -> None:
        self.post_message(self.PlaylistSelected(event.playlist))
        event.stop()
