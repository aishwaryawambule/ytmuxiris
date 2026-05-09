from __future__ import annotations

import asyncio

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option


class SearchBar(Widget):
    """Search input with debounced suggestions."""

    DEBOUNCE_MS = 300

    class Submitted(Message):
        def __init__(self, query: str, filter: str | None = None) -> None:  # noqa: A002
            super().__init__()
            self.query = query
            self.filter = filter

    class SuggestionSelected(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        widget_classes = "search-bar"
        if classes:
            widget_classes = f"{widget_classes} {classes}"
        super().__init__(name=name, id=id, classes=widget_classes, disabled=disabled)
        self._debounce_handle: asyncio.TimerHandle | None = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search songs, albums, artists…", id="search-input")
        yield OptionList(id="search-suggestions")

    def on_mount(self) -> None:
        self.query_one("#search-suggestions", OptionList).display = False

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._debounce_handle:
            self._debounce_handle.cancel()
        if len(event.value) >= 2:
            loop = asyncio.get_event_loop()
            self._debounce_handle = loop.call_later(
                self.DEBOUNCE_MS / 1000,
                lambda: asyncio.ensure_future(self._fetch_suggestions(event.value)),
            )
        else:
            self._hide_suggestions()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._hide_suggestions()
        if event.value.strip():
            self.post_message(self.Submitted(event.value.strip()))
        event.stop()

    async def _fetch_suggestions(self, query: str) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        suggestions = await api.get_search_suggestions(query)
        if not suggestions:
            self._hide_suggestions()
            return
        opt_list = self.query_one("#search-suggestions", OptionList)
        opt_list.clear_options()
        for s in suggestions[:6]:
            opt_list.add_option(Option(s, id=s))
        opt_list.display = True

    def _hide_suggestions(self) -> None:
        try:
            self.query_one("#search-suggestions", OptionList).display = False
        except Exception:
            return

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        text = str(event.option.prompt)
        self.query_one("#search-input", Input).value = text
        self._hide_suggestions()
        self.post_message(self.SuggestionSelected(text))
        event.stop()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self._hide_suggestions()
            self.query_one("#search-input", Input).value = ""
