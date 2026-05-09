from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label

from ytmuxiris.ui.widgets.album_grid import AlbumGrid
from ytmuxiris.ui.widgets.loading_spinner import LoadingSpinner
from ytmuxiris.ui.widgets.playlist_grid import PlaylistGrid
from ytmuxiris.ui.widgets.search_bar import SearchBar
from ytmuxiris.ui.widgets.song_list import SongList


class SearchView(Widget):
    """Search view with filter tabs and results.

    Only one result widget (SongList / AlbumGrid / artist list / PlaylistGrid)
    is mounted at a time inside ``#search-results-host``. Multiple ``height: 1fr``
    siblings would otherwise fight for space and collapse grid card heights.
    """

    _filter: reactive[str] = reactive("songs")
    _query: reactive[str] = reactive("")

    FILTERS = ["songs", "albums", "artists", "playlists"]

    def compose(self) -> ComposeResult:
        yield SearchBar(id="search-bar-widget")
        with Horizontal(id="filter-tabs"):
            for f in self.FILTERS:
                yield Button(
                    f.capitalize(),
                    id=f"filter-{f}",
                    classes="filter-tab" + (" active" if f == "songs" else ""),
                )
        with Vertical(id="search-results-area"):
            yield LoadingSpinner("Searching…", id="search-spinner")
            yield Vertical(id="search-results-host")
            yield Label("Enter a search query", id="search-placeholder", classes="text-muted")

    def on_mount(self) -> None:
        self.query_one("#search-spinner").display = False
        self.query_one("#search-results-host").display = False

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_search_bar_submitted(self, event: SearchBar.Submitted) -> None:
        self._query = event.query
        self._filter = event.filter or self._filter
        self._run_search()
        event.stop()

    def on_search_bar_suggestion_selected(self, event: SearchBar.SuggestionSelected) -> None:
        self._query = event.text
        self._run_search()
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("filter-"):
            new_filter = bid[len("filter-") :]
            self._filter = new_filter
            for f in self.FILTERS:
                btn = self.query_one(f"#filter-{f}", Button)
                if f == new_filter:
                    btn.add_class("active")
                else:
                    btn.remove_class("active")
            if self._query:
                self._run_search()
            event.stop()

    def on_playlist_grid_playlist_selected(self, event: PlaylistGrid.PlaylistSelected) -> None:
        from ytmuxiris.ui.screens.playlist import PlaylistScreen

        self.app.push_screen(PlaylistScreen(event.playlist.playlist_id))  # type: ignore[attr-defined]
        event.stop()

    def on_album_grid_album_selected(self, event: AlbumGrid.AlbumSelected) -> None:
        self._play_album(event.album.browse_id)
        event.stop()

    @work(exclusive=False)
    async def _play_album(self, browse_id: str) -> None:
        if not browse_id:
            return
        api = self.app.api  # type: ignore[attr-defined]
        album = await api.get_album(browse_id)
        if not album or not album.tracks:
            self.app.bell()  # type: ignore[attr-defined]
            return
        await self.app.queue.play_from(album.tracks, 0)  # type: ignore[attr-defined]

    def on_song_list_song_selected(self, event: SongList.SongSelected) -> None:
        self.run_worker(
            self.app.queue.play_from(event.songs, event.index),  # type: ignore[attr-defined]
            exclusive=False,
        )
        event.stop()

    # ------------------------------------------------------------------
    # Search worker
    # ------------------------------------------------------------------

    @work(exclusive=True)
    async def _run_search(self) -> None:
        if not self._query:
            return
        host = self.query_one("#search-results-host", Vertical)
        placeholder = self.query_one("#search-placeholder", Label)
        spinner = self.query_one("#search-spinner")

        spinner.display = True
        host.display = False
        placeholder.display = False
        await host.remove_children()

        api = self.app.api  # type: ignore[attr-defined]
        filter_ = self._filter
        empty = False

        if filter_ == "songs":
            songs = await api.search_songs(self._query, limit=30)
            empty = not songs
            if not empty:
                widget = SongList(id="search-song-list")
                await host.mount(widget)
                widget.set_songs(songs)
        elif filter_ == "albums":
            albums = await api.search_albums(self._query, limit=30)
            empty = not albums
            if not empty:
                widget = AlbumGrid(id="search-album-grid")
                await host.mount(widget)
                widget.set_albums(albums)
        elif filter_ == "artists":
            artists = await api.search_artists(self._query, limit=30)
            empty = not artists
            if not empty:
                lines = []
                for a in artists:
                    subs = f" — {a.subscriber_count}" if a.subscriber_count else ""
                    lines.append(f"{a.name}{subs}")
                widget = Label(
                    "\n".join(lines),
                    id="search-artist-list",
                    classes="search-artist-list",
                )
                await host.mount(widget)
        elif filter_ == "playlists":
            playlists = await api.search_playlists(self._query, limit=30)
            empty = not playlists
            if not empty:
                widget = PlaylistGrid(id="search-playlist-grid")
                await host.mount(widget)
                widget.set_playlists(playlists)

        spinner.display = False
        if empty:
            placeholder.update("No results found.")
            placeholder.display = True
        else:
            host.display = True
