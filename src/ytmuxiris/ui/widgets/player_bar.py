from __future__ import annotations

from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, ProgressBar

from ytmuxiris.player.audio_player import PlayerState, RepeatMode
from ytmuxiris.utils.helpers import format_duration

if TYPE_CHECKING:
    pass


class PlaybackProgressBar(Widget):
    """Clickable progress bar for seeking."""

    progress: reactive[float] = reactive(0.0)
    duration: reactive[float] = reactive(0.0)

    def render(self) -> str:
        width = max(1, self.size.width - 4)
        pct = self.progress / self.duration if self.duration > 0 else 0.0
        filled = int(width * pct)
        empty = width - filled
        return "━" * filled + "╌" * empty

    def on_click(self, event: events.Click) -> None:
        if self.duration > 0:
            pct = event.x / max(1, self.size.width)
            target = pct * self.duration
            self.app.player.seek(target)  # type: ignore[attr-defined]


class PlayerBar(Widget):
    """Bottom player bar: song info, controls, progress, volume."""

    current_song: reactive[object] = reactive(None)
    is_playing: reactive[bool] = reactive(False)
    position: reactive[float] = reactive(0.0)
    duration: reactive[float] = reactive(0.0)
    volume: reactive[int] = reactive(80)
    shuffle: reactive[bool] = reactive(False)
    repeat: reactive[RepeatMode] = reactive(RepeatMode.OFF)

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical

        with Horizontal(id="player-top-row"):
            with Vertical(id="player-song-info"):
                yield Label("Nothing playing", classes="now-playing-title", id="np-title")
                yield Label("", classes="now-playing-artist", id="np-artist")
            with Horizontal(id="player-controls"):
                yield Button("⇄", id="btn-shuffle", classes="ctrl-btn", tooltip="Shuffle (s)")
                yield Button("⏮", id="btn-prev", classes="ctrl-btn", tooltip="Previous (p)")
                yield Button(
                    "▶",
                    id="btn-play",
                    classes="ctrl-btn primary-ctrl",
                    tooltip="Play/Pause (Space)",
                )
                yield Button("⏭", id="btn-next", classes="ctrl-btn", tooltip="Next (n)")
                yield Button("↺", id="btn-repeat", classes="ctrl-btn", tooltip="Repeat (r)")
            with Horizontal(id="player-volume"):
                yield Label("🔊", classes="vol-icon", id="vol-icon")
                yield ProgressBar(total=100, id="vol-bar", show_eta=False, show_percentage=False)
                yield Label("80%", classes="vol-label", id="vol-label")
        with Horizontal(id="progress-row"):
            yield Label("0:00", classes="time-label", id="time-elapsed")
            yield PlaybackProgressBar(id="progress-bar")
            yield Label("0:00", classes="time-label", id="time-total")

    # ------------------------------------------------------------------
    # Watch handlers
    # ------------------------------------------------------------------

    def watch_current_song(self, song: object) -> None:
        if song is None:
            self.query_one("#np-title", Label).update("Nothing playing")
            self.query_one("#np-artist", Label).update("")
        else:
            from ytmuxiris.models import Song as SongModel

            if isinstance(song, SongModel):
                self.query_one("#np-title", Label).update(song.title)
                self.query_one("#np-artist", Label).update(song.artist)

    def watch_is_playing(self, playing: bool) -> None:
        icon = "⏸" if playing else "▶"
        self.query_one("#btn-play", Button).label = icon

    def watch_position(self, pos: float) -> None:
        bar = self.query_one(PlaybackProgressBar)
        bar.progress = pos
        self.query_one("#time-elapsed", Label).update(format_duration(int(pos)))

    def watch_duration(self, dur: float) -> None:
        bar = self.query_one(PlaybackProgressBar)
        bar.duration = dur
        self.query_one("#time-total", Label).update(format_duration(int(dur)))

    def watch_volume(self, vol: int) -> None:
        self.query_one("#vol-bar", ProgressBar).progress = vol
        self.query_one("#vol-label", Label).update(f"{vol}%")
        icon = "🔇" if vol == 0 else ("🔉" if vol < 50 else "🔊")
        self.query_one("#vol-icon", Label).update(icon)

    def watch_shuffle(self, on: bool) -> None:
        btn = self.query_one("#btn-shuffle", Button)
        if on:
            btn.add_class("primary-ctrl")
        else:
            btn.remove_class("primary-ctrl")

    def watch_repeat(self, mode: RepeatMode) -> None:
        btn = self.query_one("#btn-repeat", Button)
        if mode == RepeatMode.OFF:
            btn.label = "↺"
            btn.remove_class("primary-ctrl")
        elif mode == RepeatMode.ALL:
            btn.label = "↺"
            btn.add_class("primary-ctrl")
        else:
            btn.label = "↻"
            btn.add_class("primary-ctrl")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.app  # type: ignore[attr-defined]
        bid = event.button.id
        if bid == "btn-play":
            app.player.toggle()
        elif bid == "btn-next":
            self.run_worker(app.queue.next(), exclusive=False)
        elif bid == "btn-prev":
            self.run_worker(app.queue.previous(), exclusive=False)
        elif bid == "btn-shuffle":
            app.queue.toggle_shuffle()
        elif bid == "btn-repeat":
            app.queue.cycle_repeat()
        event.stop()

    def update_state(self, state: PlayerState) -> None:
        """Called from the app when player state changes."""
        self.current_song = state.current_song
        self.is_playing = state.is_playing
        self.position = state.position
        self.duration = state.duration
        self.volume = state.volume
        self.shuffle = state.shuffle
        self.repeat = state.repeat

    # ------------------------------------------------------------------
    # Scroll volume
    # ------------------------------------------------------------------

    def on_scroll_up(self, event: events.ScrollUp) -> None:
        new_vol = min(100, self.volume + 5)
        self.app.player.set_volume(new_vol)  # type: ignore[attr-defined]
        event.stop()

    def on_scroll_down(self, event: events.ScrollDown) -> None:
        new_vol = max(0, self.volume - 5)
        self.app.player.set_volume(new_vol)  # type: ignore[attr-defined]
        event.stop()
