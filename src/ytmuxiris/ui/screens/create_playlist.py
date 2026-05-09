"""Modal screen for creating a new YouTube Music playlist."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)


class CreatePlaylistScreen(ModalScreen[str | None]):
    """Modal: prompt user for title/description, create the playlist via API.

    Dismisses with the new playlist_id on success, or None on cancel/failure.
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="create-pl-dialog"):
            yield Label("Create Playlist", classes="autoplay-title")
            yield Label("Title", classes="create-pl-label")
            yield Input(placeholder="My new playlist", id="create-pl-title")
            yield Label("Description (optional)", classes="create-pl-label")
            yield Input(placeholder="What's this playlist about?", id="create-pl-desc")
            yield Label("", id="create-pl-status", classes="autoplay-status")
            with Horizontal(id="create-pl-actions"):
                yield Button("Create", id="btn-create-pl", variant="primary")
                yield Button("Cancel", id="btn-cancel-pl")

    def on_mount(self) -> None:
        self.query_one("#create-pl-title", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "create-pl-title":
            self.query_one("#create-pl-desc", Input).focus()
        else:
            self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create-pl":
            self._submit()
        elif event.button.id == "btn-cancel-pl":
            self.dismiss(None)
        event.stop()

    def _submit(self) -> None:
        title = self.query_one("#create-pl-title", Input).value.strip()
        if not title:
            self.query_one("#create-pl-status", Label).update("Title is required.")
            return
        desc = self.query_one("#create-pl-desc", Input).value.strip()
        self.query_one("#btn-create-pl", Button).disabled = True
        self.query_one("#create-pl-status", Label).update("Creating playlist…")
        self._create(title, desc)

    @work(exclusive=True)
    async def _create(self, title: str, description: str) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        pid = await api.create_playlist(title=title, description=description)
        if pid:
            try:
                self.app.notify(f"Created playlist “{title}”", timeout=3)  # type: ignore[attr-defined]
            except Exception:
                pass
            self.dismiss(pid)
        else:
            self.query_one("#create-pl-status", Label).update(
                "Failed to create playlist. Check your auth and try again."
            )
            self.query_one("#btn-create-pl", Button).disabled = False
