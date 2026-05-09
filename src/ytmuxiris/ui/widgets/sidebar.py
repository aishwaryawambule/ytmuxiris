from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, Static


class Sidebar(Widget):
    """Navigation sidebar."""

    # Icons use widely-supported Unicode glyphs that render cleanly in
    # monospace terminals (Powerline / Nerd-Font glyphs are avoided so the
    # sidebar still looks right without a custom font installed).
    ITEMS = [
        ("🏠", "Home", "home"),
        ("🔍", "Search", "search"),
        ("📚", "Library", "library"),
        ("❤", "Favorites", "favorites"),
        ("🎵", "Queue", "queue"),
        ("✨", "AI Autoplay", "autoplay"),
        ("⚙", "Settings", "settings"),
    ]

    class Navigate(Message):
        def __init__(self, screen: str) -> None:
            super().__init__()
            self.screen = screen

    def compose(self) -> ComposeResult:
        yield Static("♫ YT Music", classes="sidebar-logo")
        for icon, label, screen in self.ITEMS:
            yield _SidebarItem(icon, label, screen)

    def set_active(self, screen: str) -> None:
        for item in self.query(_SidebarItem):
            is_active = item.screen_name == screen
            if is_active:
                item.add_class("sidebar-item", "active")
            else:
                item.remove_class("active")
            try:
                marker = item.query_one(".sidebar-marker", Label)
                marker.update("♫" if is_active else " ")
            except Exception:
                pass


class _SidebarItem(Widget):
    def __init__(self, icon: str, label: str, screen_name: str) -> None:
        super().__init__(classes="sidebar-item")
        self._icon = icon
        self._label = label
        self.screen_name = screen_name

    def compose(self) -> ComposeResult:
        yield Label(" ", classes="sidebar-marker")
        yield Label(f"{self._icon} ", classes="sidebar-icon")
        yield Label(self._label, classes="sidebar-label")

    def on_click(self) -> None:
        self.post_message(Sidebar.Navigate(self.screen_name))
