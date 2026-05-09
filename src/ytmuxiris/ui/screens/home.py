from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from ytmuxiris.ui.widgets.loading_spinner import LoadingSpinner
from ytmuxiris.ui.widgets.song_list import SongList
from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)


class HomeView(Widget):
    """Home screen — renders every shelf returned by YouTube Music."""

    BINDINGS = [
        ("/", "focus_search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("Home", classes="screen-title")
        with ScrollableContainer(id="home-content"):
            yield LoadingSpinner("Loading home feed…", id="home-spinner")
            yield Vertical(id="home-sections")

    def on_mount(self) -> None:
        self.load_home_feed()

    @work(exclusive=True)
    async def load_home_feed(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        feed = await api.get_home_feed()

        try:
            spinner = self.query_one("#home-spinner", LoadingSpinner)
            spinner.display = False
        except Exception:
            pass

        sections = self.query_one("#home-sections", Vertical)
        sections.remove_children()

        shelves = feed if isinstance(feed, list) else (feed.get("shelves") or [])
        if not shelves:
            sections.mount(
                Static(
                    "Could not load home feed. Check your connection.",
                    classes="text-muted",
                )
            )
            return

        rendered_any = False
        for shelf in shelves:
            if not isinstance(shelf, dict):
                continue
            title = shelf.get("title") or "Untitled"
            contents = [c for c in (shelf.get("contents") or []) if isinstance(c, dict)]
            if not contents:
                continue

            songs = [api._parse_song(c) for c in contents if c.get("videoId")]  # noqa: SLF001
            if songs:
                sections.mount(Label(title, classes="section-header"))
                sl = SongList()
                sections.mount(sl)
                sl.set_songs(songs)
                rendered_any = True
                continue

            items = [c for c in contents if c.get("playlistId") or c.get("browseId")]
            if items:
                sections.mount(Label(title, classes="section-header"))
                sections.mount(_BrowseList(items))
                rendered_any = True

        if not rendered_any:
            sections.mount(Static("No content in your home feed yet.", classes="text-muted"))

    def on_song_list_song_selected(self, event: SongList.SongSelected) -> None:
        self.run_worker(
            self.app.queue.play_from(event.songs, event.index),  # type: ignore[attr-defined]
            exclusive=True,
            group="play",
        )
        event.stop()

    def action_focus_search(self) -> None:
        self.app.show_view("search")  # type: ignore[attr-defined]


class _BrowseList(ListView):
    """Simple list of playlist/album titles from a home shelf."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        super().__init__(classes="browse-list")
        self._items = items

    def on_mount(self) -> None:
        for item in self._items:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "Untitled"
            artists = [a for a in (item.get("artists") or []) if isinstance(a, dict)]
            subtitle = (
                ", ".join(a.get("name", "") for a in artists)
                if artists
                else (item.get("description") or "")
            )
            label = f"{title}" + (f"  •  {subtitle}" if subtitle else "")
            self.append(ListItem(Label(label)))
