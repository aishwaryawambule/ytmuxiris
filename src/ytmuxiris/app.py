from __future__ import annotations

from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.worker import WorkerState

from ytmuxiris.ai.autoplay_engine import AutoplayEngine
from ytmuxiris.ai.embeddings import EmbeddingEngine
from ytmuxiris.ai.intent_parser import IntentParser
from ytmuxiris.ai.reranker import Reranker
from ytmuxiris.api import AuthManager, YouTubeMusicAPI
from ytmuxiris.player.audio_player import AudioPlayer, PlayerState
from ytmuxiris.player.queue_manager import QueueManager
from ytmuxiris.ui.screens.autoplay_screen import AutoplayScreen
from ytmuxiris.ui.screens.favorites import FavoritesView
from ytmuxiris.ui.screens.help import HelpScreen
from ytmuxiris.ui.screens.home import HomeView
from ytmuxiris.ui.screens.library import LibraryView
from ytmuxiris.ui.screens.login import LoginScreen
from ytmuxiris.ui.screens.queue import QueueView
from ytmuxiris.ui.screens.search import SearchView
from ytmuxiris.ui.screens.settings import SettingsView
from ytmuxiris.ui.widgets.player_bar import PlayerBar
from ytmuxiris.ui.widgets.sidebar import Sidebar
from ytmuxiris.utils.cache import APICache
from ytmuxiris.utils.config import Config, load_config
from ytmuxiris.utils.favorites import FavoritesChanged, FavoritesStore
from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)

_CSS_PATH = Path(__file__).parent / "ui" / "styles" / "main.tcss"


class YTMUXIRIS(App):  # type: ignore[type-arg]
    """Root Textual application for YouTube Music TUI."""

    TITLE = "YouTube Music"
    SUB_TITLE = "Terminal UI"
    CSS_PATH = str(_CSS_PATH)

    BINDINGS = [
        # Global playback
        ("space", "toggle_play", "Play/Pause"),
        ("n", "next_track", "Next"),
        ("p", "prev_track", "Prev"),
        ("s", "toggle_shuffle", "Shuffle"),
        ("r", "cycle_repeat", "Repeat"),
        ("m", "toggle_mute", "Mute"),
        ("plus", "vol_up", "Vol+"),
        ("minus", "vol_down", "Vol-"),
        ("comma,less_than_sign", "seek_back", "Seek -10s"),
        ("full_stop,greater_than_sign", "seek_fwd", "Seek +10s"),
        # Navigation (number order matches sidebar listing)
        ("1", "go_home", "Home"),
        ("2,slash", "go_search", "Search"),
        ("3", "go_library", "Library"),
        ("4", "go_favorites", "Favorites"),
        ("f", "go_favorites", "Favorites"),
        ("5", "go_queue", "Queue"),
        ("6", "ai_autoplay", "AI Autoplay"),
        ("7", "go_settings", "Settings"),
        ("ctrl+comma", "go_settings", "Settings"),
        # AI
        ("a", "ai_autoplay", "AI Autoplay"),
        # App
        ("question_mark", "show_help", "Help"),
        ("d", "toggle_dark", "Dark mode"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config: Config = load_config()
        extra = self.config.extra
        self.auth = AuthManager()
        cache = APICache(self.config.cache_dir)
        self._cache = cache
        self.api = YouTubeMusicAPI(self.auth, cache)
        self.favorites = FavoritesStore(Path(self.config.cache_dir).parent / "favorites.json")
        self.player = AudioPlayer()
        self.queue = QueueManager(self.player, self.api)

        # AI autoplay engine
        self.autoplay_engine = AutoplayEngine(
            api=self.api,
            intent_parser=IntentParser(
                ollama_base_url=str(extra.get("ollama_url", "http://localhost:11434")),
                ollama_model=str(extra.get("ollama_model", "gpt-oss:20b")),
                claude_api_key=extra.get("claude_api_key") or None,
                claude_model=str(extra.get("claude_model", "claude-haiku-4-5-20251001")),
                prefer_frontier=bool(extra.get("use_frontier_model", False)),
            ),
            embedding_engine=EmbeddingEngine(
                ollama_base_url=str(extra.get("ollama_url", "http://localhost:11434")),
                model=str(extra.get("embed_model", "nomic-embed-text")),
                cache_dir=Path(self.config.cache_dir),
            ),
            reranker=Reranker(),
        )

        # Hook player state changes into UI
        self.player.on_state_change(self._on_player_state_change)
        self._current_view: str | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-body"):
            yield Sidebar(id="sidebar")
            yield Container(id="main-content")
        yield PlayerBar(id="player-bar")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_load(self) -> None:
        logger.info("App loading")

    def on_mount(self) -> None:
        self.run_worker(self._boot(), exclusive=True, name="boot")

    async def _boot(self) -> None:
        import asyncio as _asyncio

        # Make the queue manager aware of the app's event loop so MPV's
        # EOF callback (called from a background thread) can schedule next().
        self.queue.attach_loop(_asyncio.get_running_loop())

        ok = await self.api.authenticate()
        if not ok:
            # No saved auth. Try auto-importing cookies from the browser silently.
            logger.info("No saved auth; attempting auto cookie import")
            imported = await _asyncio.to_thread(self.auth.setup_from_browser_cookies, None)
            if imported:
                ok = await self.api.authenticate()

        if ok:
            self.show_view("home")
        else:
            # Auto-import failed — fall back to the manual login screen.
            self.push_screen(LoginScreen())

    def show_view(self, view: str) -> None:
        """Swap the center content view while keeping the app shell mounted."""
        if view == "login":
            self.push_screen(LoginScreen())
            return

        if view != "settings" and not self.api.is_authenticated():
            self.push_screen(LoginScreen())
            return

        _factories: dict[str, type] = {
            "home": HomeView,
            "search": SearchView,
            "library": LibraryView,
            "favorites": FavoritesView,
            "queue": QueueView,
            "settings": SettingsView,
        }
        view_type = _factories.get(view)
        if view_type is None:
            logger.warning("Unknown view requested: %s", view)
            return

        content = self.query_one("#main-content", Container)
        content.remove_children()
        content.mount(view_type())
        self._current_view = view

        try:
            self.query_one(Sidebar).set_active(view)
        except Exception as exc:
            logger.debug("Sidebar active update skipped: %s", exc)

    def on_unmount(self) -> None:
        self.player.terminate()
        logger.info("App unmounted")

    def logout(self) -> None:
        """Sign out: delete auth token, clear all cached data, show login screen."""
        self.player.stop()
        self.queue.clear()
        self.auth.logout()
        self._cache.invalidate_all()
        self._current_view = None
        try:
            content = self.query_one("#main-content", Container)
            content.remove_children()
        except Exception:
            pass
        self.push_screen(LoginScreen())

    # ------------------------------------------------------------------
    # Player state → UI (called from MPV thread via call_from_thread)
    # ------------------------------------------------------------------

    def _on_player_state_change(self, state: PlayerState) -> None:
        # _notify_state can be invoked from the MPV background thread (most
        # often) or from the asyncio loop thread (e.g. when QueueManager
        # toggles shuffle/repeat synchronously). call_from_thread only works
        # from a non-loop thread; fall back to a direct dispatch otherwise.
        try:
            self.call_from_thread(self._apply_player_state, state)
        except Exception:
            self._apply_player_state(state)

    def _apply_player_state(self, state: PlayerState) -> None:
        try:
            bar = self.query_one(PlayerBar)
            bar.update_state(state)
        except Exception as exc:
            logger.debug("PlayerBar update skipped: %s", exc)

    # ------------------------------------------------------------------
    # Sidebar navigation
    # ------------------------------------------------------------------

    def on_sidebar_navigate(self, event: Sidebar.Navigate) -> None:  # type: ignore[name-defined]
        if event.screen == "autoplay":
            self.action_ai_autoplay()
        else:
            self.show_view(event.screen)
        event.stop()

    def on_song_row_add_to_playlist(self, event) -> None:  # type: ignore[no-untyped-def]
        from ytmuxiris.ui.screens.add_to_playlist import AddToPlaylistScreen

        self.push_screen(AddToPlaylistScreen(event.song))
        event.stop()

    def on_favorites_changed(self, event: FavoritesChanged) -> None:
        from ytmuxiris.ui.widgets.song_list import SongList

        for sl in self.query(SongList):
            sl.refresh_liked_state(event.song.video_id, event.liked)
        try:
            view = self.query_one(FavoritesView)
        except Exception:
            return
        view._refresh()

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------

    def on_resize(self, event: events.Resize) -> None:
        if event.size.width < 80:
            self.add_class("compact")
        else:
            self.remove_class("compact")

    # ------------------------------------------------------------------
    # Worker error boundary
    # ------------------------------------------------------------------

    def on_worker_state_changed(self, event: object) -> None:
        if hasattr(event, "state") and event.state == WorkerState.ERROR:  # type: ignore[attr-defined]
            if hasattr(event, "worker") and hasattr(event.worker, "error"):
                logger.error("Worker error: %s", event.worker.error)

    # ------------------------------------------------------------------
    # Actions — playback
    # ------------------------------------------------------------------

    def action_toggle_play(self) -> None:
        self.player.toggle()

    def action_next_track(self) -> None:
        self.run_worker(self.queue.next(), exclusive=False)

    def action_prev_track(self) -> None:
        self.run_worker(self.queue.previous(), exclusive=False)

    def action_toggle_shuffle(self) -> None:
        self.queue.toggle_shuffle()

    def action_cycle_repeat(self) -> None:
        self.queue.cycle_repeat()

    def action_toggle_mute(self) -> None:
        self.player.toggle_mute()

    def action_vol_up(self) -> None:
        new_vol = min(100, self.player.state.volume + 5)
        self.player.set_volume(new_vol)

    def action_vol_down(self) -> None:
        new_vol = max(0, self.player.state.volume - 5)
        self.player.set_volume(new_vol)

    def action_seek_back(self) -> None:
        self.player.seek_relative(-10)

    def action_seek_fwd(self) -> None:
        self.player.seek_relative(10)

    # ------------------------------------------------------------------
    # Actions — navigation
    # ------------------------------------------------------------------

    def action_go_home(self) -> None:
        self.show_view("home")

    def action_go_search(self) -> None:
        self.show_view("search")

        def _focus_input() -> None:
            try:
                from textual.widgets import Input

                self.query_one("#search-input", Input).focus()
            except Exception as exc:
                logger.debug("Search input focus skipped: %s", exc)

        # The view mounts asynchronously, so defer focus until after compose.
        self.call_after_refresh(_focus_input)

    def action_go_library(self) -> None:
        self.show_view("library")

    def action_go_favorites(self) -> None:
        self.show_view("favorites")

    def action_go_queue(self) -> None:
        self.show_view("queue")

    def action_go_settings(self) -> None:
        self.show_view("settings")

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_ai_autoplay(self) -> None:
        self.push_screen(AutoplayScreen())

    def action_quit(self) -> None:
        self.player.terminate()
        self.exit()
