"""Generic yes/no confirmation modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """Modal that asks the user to confirm a destructive action."""

    BINDINGS = [
        ("escape", "dismiss_no", "Cancel"),
        ("y", "confirm", "Yes"),
        ("n", "dismiss_no", "No"),
    ]

    def __init__(self, title: str, body: str = "") -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._title, classes="autoplay-title")
            if self._body:
                yield Label(self._body, classes="text-muted")
            with Horizontal(id="confirm-actions"):
                yield Button("Confirm", id="btn-confirm-yes", variant="error")
                yield Button("Cancel", id="btn-confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
        event.stop()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_dismiss_no(self) -> None:
        self.dismiss(False)
