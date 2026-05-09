from __future__ import annotations

import itertools

from textual.timer import Timer
from textual.widgets import Static


class LoadingSpinner(Static):
    """Animated Braille spinner for loading states."""

    FRAMES = ["⠋", "⠙", "⠸", "⢰", "⣠", "⣄", "⡆", "⠇"]

    def __init__(
        self,
        text: str = "Loading…",
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        widget_classes = "loading-spinner"
        if classes:
            widget_classes = f"{widget_classes} {classes}"
        super().__init__(classes=widget_classes, name=name, id=id, disabled=disabled)
        self._text = text
        self._frames = itertools.cycle(self.FRAMES)
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.1, self._tick)

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    def _tick(self) -> None:
        frame = next(self._frames)
        self.update(f"[red]{frame}[/] {self._text}")
