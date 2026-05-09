from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Label, TabbedContent, TabPane

from ytmuxiris.ui.screens.create_playlist import CreatePlaylistScreen
from ytmuxiris.ui.screens.playlist import PlaylistScreen
from ytmuxiris.ui.widgets.album_grid import AlbumGrid
from ytmuxiris.ui.widgets.loading_spinner import LoadingSpinner
from ytmuxiris.ui.widgets.playlist_grid import PlaylistGrid
from ytmuxiris.ui.widgets.song_list import SongList


class LibraryView(Widget):
    """Library view with Songs, Albums, Artists, Playlists tabs."""

    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("ctrl+n", "new_playlist", "New playlist"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("Library", classes="screen-title")
        with TabbedContent():
            with TabPane("Songs", id="tab-songs"):
                yield LoadingSpinner("Loading songs…", id="lib-songs-spinner")
                yield SongList(id="lib-song-list")
            with TabPane("Albums", id="tab-albums"):
                yield LoadingSpinner("Loading albums…", id="lib-albums-spinner")
                yield AlbumGrid(id="lib-album-grid")
            with TabPane("Artists", id="tab-artists"):
                yield LoadingSpinner("Loading artists…", id="lib-artists-spinner")
                yield Label("", id="lib-artists-list")
            with TabPane("Playlists", id="tab-playlists"):
                with Horizontal(id="lib-playlists-actions"):
                    yield Button(
                        "+ New Playlist",
                        id="btn-new-playlist",
                        classes="settings-btn primary",
                    )
                    yield Button(
                        "↻ Refresh",
                        id="btn-refresh-playlists",
                        classes="settings-btn",
                    )
                yield LoadingSpinner("Loading playlists…", id="lib-playlists-spinner")
                yield PlaylistGrid(id="lib-playlists-grid")

    def on_mount(self) -> None:
        self.load_songs()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane_id = event.pane.id if event.pane else None
        if pane_id == "tab-songs":
            self.load_songs()
        elif pane_id == "tab-albums":
            self.load_albums()
        elif pane_id == "tab-artists":
            self.load_artists()
        elif pane_id == "tab-playlists":
            self.load_playlists()

    @work(exclusive=True)
    async def load_songs(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        songs = await api.get_library_songs()
        self.query_one("#lib-songs-spinner").display = False
        song_list = self.query_one("#lib-song-list", SongList)
        song_list.set_songs(songs)

    @work(exclusive=True)
    async def load_albums(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        albums = await api.get_library_albums()
        self.query_one("#lib-albums-spinner").display = False
        self.query_one("#lib-album-grid", AlbumGrid).set_albums(albums)

    @work(exclusive=True)
    async def load_artists(self) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        artists = await api.get_library_artists()
        self.query_one("#lib-artists-spinner").display = False
        names = "\n".join(a.name for a in artists)
        self.query_one("#lib-artists-list", Label).update(names or "No artists found")

    @work(exclusive=True, group="library-playlists")
    async def load_playlists(self, force: bool = False) -> None:
        api = self.app.api  # type: ignore[attr-defined]
        if force:
            try:
                self.app._cache.invalidate_library()  # type: ignore[attr-defined]
            except Exception:
                pass
        spinner = self.query_one("#lib-playlists-spinner")
        spinner.display = True
        playlists = await api.get_library_playlists()
        spinner.display = False
        self.query_one("#lib-playlists-grid", PlaylistGrid).set_playlists(playlists)

    def on_song_list_song_selected(self, event: SongList.SongSelected) -> None:
        self.run_worker(
            self.app.queue.play_from(event.songs, event.index),  # type: ignore[attr-defined]
            exclusive=False,
        )
        event.stop()

    def on_playlist_grid_playlist_selected(self, event: PlaylistGrid.PlaylistSelected) -> None:
        self.app.push_screen(PlaylistScreen(event.playlist.playlist_id))  # type: ignore[attr-defined]
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new-playlist":
            self.action_new_playlist()
            event.stop()
        elif event.button.id == "btn-refresh-playlists":
            self.load_playlists(force=True)
            event.stop()

    def action_focus_search(self) -> None:
        self.app.show_view("search")  # type: ignore[attr-defined]

    def action_new_playlist(self) -> None:
        def _after(playlist_id: str | None) -> None:
            if playlist_id:
                self.load_playlists(force=True)

        self.app.push_screen(CreatePlaylistScreen(), _after)  # type: ignore[attr-defined]
