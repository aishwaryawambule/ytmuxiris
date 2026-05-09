from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label

from ytmuxiris.models import Song
from ytmuxiris.utils.helpers import format_duration


class _QueueItem(Label):
    class Clicked(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(
        self,
        song: Song,
        queue_index: int,
        display_position: int,
        current: bool,
    ) -> None:
        marker = "♫ " if current else f"{display_position}. "
        text = f"{marker}{song.title} — {song.artist}  [{format_duration(song.duration)}]"
        super().__init__(
            text,
            classes="queue-item" + (" current" if current else ""),
        )
        self._index = queue_index

    def on_click(self) -> None:
        self.post_message(self.Clicked(self._index))


class QueueView(Widget):
    """Queue view."""

    BINDINGS = [
        ("c", "clear_queue", "Clear queue"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue-header"):
            yield Label("Queue", classes="screen-title")
            yield Button("Clear", id="btn-clear-queue", classes="ctrl-btn")
        with ScrollableContainer(id="queue-list"):
            yield Label("Queue is empty", id="queue-empty-msg", classes="text-muted")

    def on_mount(self) -> None:
        self._refresh_pending = False
        # Auto-refresh whenever the queue changes (add, remove, advance, clear).
        queue_mgr = self.app.queue  # type: ignore[attr-defined]
        queue_mgr.on_change(self._on_queue_changed)
        # Defer the first render until after the DOM has fully settled.
        # When the user navigates back to this view, the parent container
        # tears down the old QueueView and mounts a fresh one; querying
        # #queue-list synchronously inside on_mount can race with that
        # remount and silently drop the songs.
        self._refresh_pending = True
        try:
            self.app.call_after_refresh(self._do_refresh)  # type: ignore[attr-defined]
        except Exception:
            self._refresh_pending = False
            self._refresh_queue()

    def on_unmount(self) -> None:
        try:
            self.app.queue.off_change(self._on_queue_changed)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_queue_changed(self) -> None:
        # Coalesce bursts of mutations into one refresh so we don't race
        # remove_children/mount and end up with duplicate widget IDs.
        if not self.is_mounted or getattr(self, "_refresh_pending", False):
            return
        self._refresh_pending = True
        try:
            self.app.call_later(self._do_refresh)  # type: ignore[attr-defined]
        except Exception:
            self._refresh_pending = False

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_queue()

    def _refresh_queue(self) -> None:
        # The change callback can fire after the user navigates away and this
        # widget is no longer mounted; skip silently in that case.
        if not self.is_mounted:
            return
        queue_mgr = self.app.queue  # type: ignore[attr-defined]
        try:
            container = self.query_one("#queue-list", ScrollableContainer)
        except Exception:
            return
        container.remove_children()

        songs = queue_mgr.queue
        current_idx = queue_mgr.current_index

        if not songs:
            container.mount(Label("Queue is empty", classes="text-muted"))
            return

        # Render order: currently-playing song pinned to the top, then the
        # upcoming songs (queue[current+1:]), then any songs that came before
        # the current one. The actual queue order in QueueManager is left
        # untouched — only the display is reshuffled.
        if 0 <= current_idx < len(songs):
            order = (
                [current_idx]
                + list(range(current_idx + 1, len(songs)))
                + list(range(0, current_idx))
            )
        else:
            order = list(range(len(songs)))

        for display_pos, queue_idx in enumerate(order, start=1):
            song = songs[queue_idx]
            is_current = queue_idx == current_idx
            container.mount(_QueueItem(song, queue_idx, display_pos, is_current))

    def on__queue_item_clicked(self, event: _QueueItem.Clicked) -> None:
        queue_mgr = self.app.queue  # type: ignore[attr-defined]
        songs = queue_mgr.queue
        if 0 <= event.index < len(songs):
            self.run_worker(queue_mgr.play_now(songs[event.index]), exclusive=False)
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-clear-queue":
            self.action_clear_queue()
        event.stop()

    def action_clear_queue(self) -> None:
        self.app.queue.clear()  # type: ignore[attr-defined]
        self._refresh_queue()
