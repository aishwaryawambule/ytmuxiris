from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

_BINDINGS = [
    (
        "Playback",
        [
            ("Space", "Play / Pause"),
            ("n", "Next track"),
            ("p", "Previous track"),
            ("s", "Toggle shuffle"),
            ("r", "Cycle repeat mode"),
            ("m", "Toggle mute"),
            ("+ / -", "Volume up / down"),
            (", / .", "Seek -10s / +10s"),
        ],
    ),
    (
        "Navigation",
        [
            ("1", "Go to Home"),
            ("2", "Go to Search"),
            ("3", "Go to Library"),
            ("4  /  f", "Go to Favorites"),
            ("5", "Go to Queue"),
            ("6  /  a", "AI Autoplay"),
            ("7  /  Ctrl+,", "Go to Settings"),
            ("Escape", "Go back"),
            ("/", "Focus search bar"),
        ],
    ),
    (
        "App",
        [
            ("?", "Show this help"),
            ("q", "Quit"),
            ("d", "Toggle dark mode"),
        ],
    ),
]


class HelpScreen(ModalScreen):
    """Keyboard shortcuts reference."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("?", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("Keyboard Shortcuts", classes="help-title")
            for section, rows in _BINDINGS:
                yield Label(section, classes="help-section")
                for key, desc in rows:
                    with Horizontal(classes="help-row"):
                        yield Label(key, classes="help-key")
                        yield Label(desc, classes="help-desc")
            yield Button("Close  [Esc]", id="help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close":
            self.dismiss()
