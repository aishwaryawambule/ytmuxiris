from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static


class LoginScreen(Screen):
    """Sign-in screen — imports session from your browser automatically."""

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        with Vertical(id="login-card"):
            yield Label("♫ YouTube Music TUI", classes="login-title")
            yield Static(
                "Sign in by importing your existing browser session.\n"
                "Make sure you are logged in to music.youtube.com in\n"
                "Chrome, Firefox, Brave, or Edge.",
                classes="login-instructions",
            )
            yield Button("Import from Browser", id="btn-oauth", classes="login-btn")
            yield Label("", id="login-status", classes="login-status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-oauth":
            self._start()
        event.stop()

    def _start(self) -> None:
        self._set_status("Looking for browser session…")
        self.query_one("#btn-oauth", Button).disabled = True
        self._do_login()

    @work(exclusive=True)
    async def _do_login(self) -> None:
        import asyncio

        auth = self.app.auth  # type: ignore[attr-defined]

        def status_cb(msg: str) -> None:
            self.app.call_from_thread(self._set_status, msg)  # type: ignore[attr-defined]

        try:
            success = await asyncio.to_thread(auth.setup_from_browser_cookies, status_cb)
        except Exception as exc:
            self.notify(f"Error: {exc}", severity="error", timeout=10)
            self.query_one("#btn-oauth", Button).disabled = False
            self._set_status("")
            return

        if not success:
            self.notify(
                auth.last_error or "Could not find a browser session.",
                severity="error",
                timeout=12,
            )
            self.query_one("#btn-oauth", Button).disabled = False
            self._set_status("")
            return

        ok = await self.app.api.authenticate()  # type: ignore[attr-defined]
        if ok:
            # Drop any cache from the previous session so the UI reflects the
            # account that's actually signed in (home feed, library, etc.).
            try:
                self.app._cache.invalidate_all()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.notify("Signed in to YouTube Music!", severity="information")

            def _go_home() -> None:
                try:
                    self.app.pop_screen()  # type: ignore[attr-defined]
                except Exception:
                    pass
                self.app.show_view("home")  # type: ignore[attr-defined]

            self.app.call_later(_go_home)  # type: ignore[attr-defined]
            return
        else:
            self.notify(
                auth.last_error or "Authentication failed. Please try again.",
                severity="error",
                timeout=10,
            )
            self.query_one("#btn-oauth", Button).disabled = False
            self._set_status("")

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#login-status", Label).update(message)
        except Exception:
            pass
