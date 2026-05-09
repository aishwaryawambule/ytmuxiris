from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

if TYPE_CHECKING:
    from ytmuxiris.models import Album


class AlbumCard(Widget):
    """Card widget for a single album."""

    class Selected(Message):
        def __init__(self, album: Album) -> None:
            super().__init__()
            self.album = album

    def __init__(self, album: Album) -> None:
        super().__init__(classes="album-card")
        self.album = album

    def compose(self) -> ComposeResult:
        yield Label("◉", classes="album-art-placeholder")
        yield Label(self.album.title, classes="album-title")
        yield Label(self.album.artist, classes="album-artist")
        if self.album.year:
            yield Label(self.album.year, classes="album-year")

    def on_click(self) -> None:
        self.post_message(self.Selected(self.album))


class AlbumGrid(Widget):
    """Grid of AlbumCard widgets."""

    class AlbumSelected(Message):
        def __init__(self, album: Album) -> None:
            super().__init__()
            self.album = album

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        widget_classes = "album-grid"
        if classes:
            widget_classes = f"{widget_classes} {classes}"
        super().__init__(name=name, id=id, classes=widget_classes, disabled=disabled)
        self._albums: list[Album] = []

    def compose(self) -> ComposeResult:
        return iter([])

    def set_albums(self, albums: list[Album]) -> None:
        self._albums = albums
        self.remove_children()
        for album in albums:
            self.mount(AlbumCard(album))

    def on_album_card_selected(self, event: AlbumCard.Selected) -> None:
        self.post_message(self.AlbumSelected(event.album))
        event.stop()
