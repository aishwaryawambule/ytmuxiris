"""Drive the TUI headlessly with Textual's Pilot to verify UI plumbing.

Run: poetry run python scripts/ui_smoke.py
"""
from __future__ import annotations

import asyncio
import sys

from ytmuxiris.app import YTMUXIRIS
from ytmuxiris.models import Song
from ytmuxiris.ui.widgets.player_bar import PlayerBar
from ytmuxiris.ui.widgets.sidebar import Sidebar


def _song(i: int) -> Song:
    return Song(
        video_id=f"vid{i}",
        title=f"Track {i}",
        artist="Tester",
        album="Album",
        duration=180,
        thumbnail=None,
    )


async def main() -> int:
    app = YTMUXIRIS()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  PASS  {name}  {detail}")
        else:
            print(f"  FAIL  {name}  {detail}")
            failures.append(name)

    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        # Wait for the boot worker (auth + initial view) to finish.
        for _ in range(40):
            await pilot.pause()
            if app.api.is_authenticated():
                break
            await asyncio.sleep(0.1)

        # Auth should be set up at this point — skip the LoginScreen if it pushed.
        if app.api.is_authenticated():
            print("\n=== Sidebar / view switching ===")
            for view in ["search", "library", "queue", "home"]:
                app.show_view(view)
                await pilot.pause()
                sidebar = app.query_one(Sidebar)
                actives = [
                    item.screen_name
                    for item in sidebar.query("_SidebarItem")
                    if "active" in item.classes
                ]
                check(
                    f"sidebar active == {view!r}",
                    actives == [view],
                    f"got {actives}",
                )

            print("\n=== PlayerBar reflects shuffle/repeat toggles ===")
            app.show_view("queue")
            await pilot.pause()
            app.queue.add(_song(1))
            app.queue.add(_song(2))
            await pilot.pause()
            check("queue length after add", len(app.queue.queue) == 2)

            app.action_toggle_shuffle()
            for _ in range(5):
                await pilot.pause()
                await asyncio.sleep(0.05)
            bar = app.query_one(PlayerBar)
            check(
                "PlayerBar.shuffle toggled",
                bar.shuffle is True,
                f"queue.shuffle={app.queue.shuffle} player.shuffle={app.player.state.shuffle} bar.shuffle={bar.shuffle}",
            )

            app.action_cycle_repeat()
            for _ in range(5):
                await pilot.pause()
                await asyncio.sleep(0.05)
            check(
                "PlayerBar.repeat advanced",
                bar.repeat.value in ("all", "one"),
                f"queue.repeat={app.queue.repeat.value} bar.repeat={bar.repeat.value}",
            )

            print("\n=== QueueView auto-refreshes when queue mutates ===")
            from ytmuxiris.ui.screens.queue import QueueView, _QueueItem
            view_widget = app.query_one(QueueView)
            before = len(view_widget.query(_QueueItem))
            app.queue.add(_song(3))
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()
            after = len(view_widget.query(_QueueItem))
            check(
                "QueueView item count grew",
                after == before + 1,
                f"{before} -> {after}",
            )
        else:
            print("Not authenticated — skipping UI checks.")
            failures.append("auth")

    print(f"\n{len(failures)} failures")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
