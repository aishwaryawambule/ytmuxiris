"""End-to-end smoke test that exercises every feature without driving the TUI.

Run with: poetry run python scripts/smoke.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import traceback
from pathlib import Path

from ytmuxiris.ai.autoplay_engine import AutoplayEngine
from ytmuxiris.ai.embeddings import EmbeddingEngine
from ytmuxiris.ai.intent_parser import IntentParser
from ytmuxiris.ai.reranker import Reranker
from ytmuxiris.api import AuthManager, YouTubeMusicAPI
from ytmuxiris.player.audio_player import AudioPlayer
from ytmuxiris.player.queue_manager import QueueManager
from ytmuxiris.utils.cache import APICache


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.rows.append((name, True, detail))
        print(f"  PASS  {name}  {detail}")

    def fail(self, name: str, detail: str) -> None:
        self.rows.append((name, False, detail))
        print(f"  FAIL  {name}  {detail}")

    def section(self, title: str) -> None:
        print(f"\n=== {title} ===")

    def summary(self) -> int:
        passed = sum(1 for _, ok, _ in self.rows if ok)
        failed = sum(1 for _, ok, _ in self.rows if not ok)
        print(f"\n{passed} passed, {failed} failed")
        return 0 if failed == 0 else 1


async def run() -> int:
    r = Result()
    cache_dir = Path(tempfile.mkdtemp(prefix="smoke-cache-"))
    auth = AuthManager()
    cache = APICache(str(cache_dir))
    api = YouTubeMusicAPI(auth, cache)

    # -- Auth ---------------------------------------------------------------
    r.section("Auth & account sync")
    if not auth.is_authenticated():
        r.fail("auth.is_authenticated", "No auth.json — log in via the app first.")
        return r.summary()
    r.ok("auth.is_authenticated")

    ok = await api.authenticate()
    r.ok("api.authenticate", "ok" if ok else "FAILED")
    if not ok:
        return r.summary()

    # -- Search -------------------------------------------------------------
    r.section("Search")
    try:
        songs = await api.search_songs("daft punk", limit=5)
        if songs:
            r.ok("search_songs", f"{len(songs)} hits, first={songs[0].title!r}")
        else:
            r.fail("search_songs", "empty result")
    except Exception as e:
        r.fail("search_songs", f"{e}")

    # -- Library (account sync) --------------------------------------------
    r.section("Library — should mirror the signed-in account")
    try:
        lib_songs = await api.get_library_songs(limit=20)
        r.ok("get_library_songs", f"{len(lib_songs)} tracks")
    except Exception as e:
        r.fail("get_library_songs", f"{e}")
        lib_songs = []

    try:
        playlists = await api.get_library_playlists(limit=20)
        r.ok("get_library_playlists", f"{len(playlists)} playlists")
    except Exception as e:
        r.fail("get_library_playlists", f"{e}")

    # -- Home feed (recommendations) ---------------------------------------
    try:
        feed = await api.get_home_feed()
        if feed:
            r.ok("get_home_feed", f"{len(feed)} shelves")
        else:
            r.fail("get_home_feed", "empty")
    except Exception as e:
        r.fail("get_home_feed", f"{e}")

    # -- Stream URL extraction (the prior root-cause failure) --------------
    r.section("Stream URL extraction (yt-dlp)")
    sample = songs[0] if songs else (lib_songs[0] if lib_songs else None)
    if sample is None:
        r.fail("stream_url", "no song available")
    else:
        try:
            url = await api.get_stream_url(sample.video_id)
            if url and url.startswith("http"):
                r.ok("get_stream_url", f"video={sample.video_id} ok")
            else:
                r.fail("get_stream_url", f"no url for {sample.video_id}")
        except Exception as e:
            r.fail("get_stream_url", f"{e}")

    # -- Queue manager -----------------------------------------------------
    r.section("QueueManager — add/remove/shuffle/repeat/advance")
    player = AudioPlayer()
    queue = QueueManager(player, api)
    queue.attach_loop(asyncio.get_running_loop())

    change_events: list[int] = []
    queue.on_change(lambda: change_events.append(len(queue.queue)))

    pool = (songs or lib_songs)[:4]
    if len(pool) < 3:
        r.fail("queue_setup", "need 3+ songs to test")
    else:
        queue.add(pool[0]); queue.add(pool[1]); queue.add(pool[2])
        if len(queue.queue) == 3 and len(change_events) == 3:
            r.ok("queue.add", "3 added, observers fired")
        else:
            r.fail("queue.add", f"queue={len(queue.queue)} events={len(change_events)}")

        queue.remove(1)
        if len(queue.queue) == 2:
            r.ok("queue.remove")
        else:
            r.fail("queue.remove", f"{len(queue.queue)}")

        before = queue.shuffle
        queue.toggle_shuffle()
        r.ok("queue.toggle_shuffle", f"{before} -> {queue.shuffle}")

        before_r = queue.repeat
        queue.cycle_repeat()
        r.ok("queue.cycle_repeat", f"{before_r.value} -> {queue.repeat.value}")

        # Verify shuffle/repeat propagated into PlayerState (so the PlayerBar updates).
        st = player.state
        if st.shuffle == queue.shuffle and st.repeat == queue.repeat:
            r.ok("queue->player_state sync")
        else:
            r.fail("queue->player_state sync",
                   f"player.shuffle={st.shuffle} expected={queue.shuffle}; "
                   f"player.repeat={st.repeat} expected={queue.repeat}")

        queue.clear()
        r.ok("queue.clear", f"len={len(queue.queue)}")

    # -- Autoplay engine ---------------------------------------------------
    r.section("AI Autoplay")
    engine = AutoplayEngine(
        api=api,
        intent_parser=IntentParser(),
        embedding_engine=EmbeddingEngine(),
        reranker=Reranker(),
    )
    try:
        result_songs = await engine.run("upbeat french electronic")
        if result_songs:
            r.ok("autoplay.run", f"{len(result_songs)} songs queued, first={result_songs[0].title!r}")
        else:
            r.fail("autoplay.run", "no songs returned")
    except Exception as e:
        traceback.print_exc()
        r.fail("autoplay.run", f"{e}")

    # -- Mini playback test (don't spam audio — just kick mpv & stop quickly)
    r.section("Audio player — load a stream URL")
    try:
        if sample is not None:
            url = await api.get_stream_url(sample.video_id)
            if url:
                player.play(url, sample)
                await asyncio.sleep(2.5)
                state = player.state
                player.stop()
                if state.current_song is not None:
                    r.ok("player.play+state", f"playing={state.is_playing} pos={state.position:.2f}s")
                else:
                    r.fail("player.play+state", "current_song never set")
            else:
                r.fail("player.play", "no stream url")
    except Exception as e:
        r.fail("player.play", f"{e}")
    finally:
        player.terminate()

    return r.summary()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
