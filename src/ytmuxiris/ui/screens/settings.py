from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Select, Static, Switch

from ytmuxiris.utils.config import Config, save_config


class SettingsView(Widget):
    """Settings view."""

    def compose(self) -> ComposeResult:
        config: Config = self.app.config  # type: ignore[attr-defined]
        yield Label("Settings", classes="screen-title")
        with Vertical(classes="settings-group"):
            yield Static("Audio", classes="settings-group-title")
            yield _SettingRow(
                "Audio Quality",
                Select(
                    [("Low", "low"), ("Medium", "medium"), ("High", "high")],
                    value=config.audio_quality,
                    id="sel-quality",
                ),
            )
        with Vertical(classes="settings-group"):
            yield Static("Playback", classes="settings-group-title")
            yield _SettingRow(
                "Shuffle on start",
                Switch(value=config.shuffle, id="sw-shuffle"),
            )
        with Vertical(classes="settings-group"):
            yield Static("Account", classes="settings-group-title")
            yield Button("Sign out", id="btn-signout", classes="settings-btn danger")
        yield Button("Save settings", id="btn-save", classes="settings-btn primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-save":
            self._save()
        elif bid == "btn-signout":
            self.app.logout()  # type: ignore[attr-defined]
        event.stop()

    def _save(self) -> None:
        config: Config = self.app.config  # type: ignore[attr-defined]
        try:
            config.audio_quality = str(self.query_one("#sel-quality", Select).value)
            config.shuffle = bool(self.query_one("#sw-shuffle", Switch).value)
            save_config(config)
            self.notify("Settings saved.", severity="information")
        except Exception as e:
            self.notify(f"Failed to save settings: {e}", severity="error")


class _SettingRow(Static):
    def __init__(self, label: str, control: object) -> None:
        super().__init__(classes="settings-row")
        self._label = label
        self._control = control

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="settings-label")
        yield self._control  # type: ignore[misc]
