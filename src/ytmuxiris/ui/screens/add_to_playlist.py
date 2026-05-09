"""Modal screen: pick a library playlist to add a song to."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView

from ytmuxiris.models import Playlist, Song
from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)


class AddToPlaylistScreen(ModalScreen[str | None]):
    """Pick one of the user's playlists to add ``song`` to.

    Dismisses with the chosen playlist_id on success, or None on cancel/failure.
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, song: Song) -> None:
        super().__init__()
        self._song = song
        self._playlists: list[Playlist] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="add-to-pl-dialog"):
            yield Label("Add to Playlist", classes="autoplay-title")
            yield Label(
                f"“{self._song.title}” — {self._song.artist}",
                id="add-to-pl-song",
                classes="text-muted",
            )
            yield Label("Loading playlists…", id="add-to-pl-status", classes="autoplay-status")
            yield ListView(id="add-to-pl-list")
            with Horizontal(id="add-to-pl-actions"):
                yield Button("Cancel", id="btn-cancel-addpl")

    def on_mount(self) -> None:
        self._load_playlists()

    @work(exclusive=True)
    async def _load_playlists(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        playlists = await api.get_library_playlists()
        self._playlists = playlists or []
        lv = self.query_one("#add-to-pl-list", ListView)
        await lv.clear()
        if not self._playlists:
            self.query_one("#add-to-pl-status", Label).update(
                "No playlists yet. Create one from Library first."
            )
            return
        self.query_one("#add-to-pl-status", Label).update("Select a playlist:")
        for pl in self._playlists:
            count = f" ({pl.track_count})" if pl.track_count else ""
            await lv.append(ListItem(Label(f"{pl.title}{count}")))
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is None or idx < 0 or idx >= len(self._playlists):
            return
        pl = self._playlists[idx]
        self.query_one("#add-to-pl-status", Label).update(f"Adding to “{pl.title}”…")
        self._add(pl.playlist_id, pl.title)
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel-addpl":
            self.dismiss(None)
        event.stop()

    @work(exclusive=True)
    async def _add(self, playlist_id: str, playlist_title: str) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        ok = await api.add_to_playlist(playlist_id, [self._song.video_id])
        if ok:
            try:
                self.app.notify(  # type: ignore[attr-defined]
                    f"Added “{self._song.title}” to “{playlist_title}”",
                    timeout=3,
                )
            except Exception:
                pass
            self.dismiss(playlist_id)
        else:
            self.query_one("#add-to-pl-status", Label).update(
                "Failed to add. Check your auth and try again."
            )
