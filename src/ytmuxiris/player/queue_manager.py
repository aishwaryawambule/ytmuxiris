from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import TYPE_CHECKING

from ytmuxiris.player.audio_player import AudioPlayer, RepeatMode
from ytmuxiris.utils.logger import get_logger

if TYPE_CHECKING:
    from ytmuxiris.api import YouTubeMusicAPI
    from ytmuxiris.models import Song

logger = get_logger(__name__)


class QueueManager:
    """Manages playback queue with shuffle, repeat, and history."""

    def __init__(self, player: AudioPlayer, api: YouTubeMusicAPI) -> None:
        self._player = player
        self._api = api
        self._queue: list[Song] = []
        self._history: list[Song] = []
        self._current_index: int = -1
        self._shuffle_order: list[int] = []
        self._shuffle: bool = False
        self._repeat: RepeatMode = RepeatMode.OFF
        self._loop: asyncio.AbstractEventLoop | None = None
        self._change_callbacks: list[Callable[[], None]] = []

        self._player.on_track_end(self._on_track_end)

    # ------------------------------------------------------------------
    # Loop / change subscriptions
    # ------------------------------------------------------------------

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def on_change(self, cb: Callable[[], None]) -> None:
        self._change_callbacks.append(cb)

    def off_change(self, cb: Callable[[], None]) -> None:
        try:
            self._change_callbacks.remove(cb)
        except ValueError:
            pass

    def _notify_change(self) -> None:
        for cb in list(self._change_callbacks):
            try:
                cb()
            except Exception as e:
                logger.debug("Queue change callback error: %s", e)

    # ------------------------------------------------------------------
    # Queue manipulation
    # ------------------------------------------------------------------

    def add(self, song: Song) -> None:
        was_idle = self.current_song is None
        self._queue.append(song)
        if was_idle:
            self._current_index = len(self._queue) - 1
            self._schedule_play_current()
        self._notify_change()

    def add_next(self, song: Song) -> None:
        was_idle = self.current_song is None
        insert_at = self._current_index + 1 if not was_idle else len(self._queue)
        self._queue.insert(insert_at, song)
        if was_idle:
            self._current_index = insert_at
            self._schedule_play_current()
        self._notify_change()

    def add_multiple(self, songs: list[Song]) -> None:
        if not songs:
            return
        was_idle = self.current_song is None
        start_idx = len(self._queue)
        self._queue.extend(songs)
        if was_idle:
            self._current_index = start_idx
            self._schedule_play_current()
        self._notify_change()

    def _schedule_play_current(self) -> None:
        """Dispatch _play_current onto the event loop from any thread."""
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop
            except RuntimeError:
                logger.debug("autoplay: no running loop attached, skipping")
                return
        try:
            asyncio.run_coroutine_threadsafe(self._play_current(), loop)
        except Exception as e:
            logger.debug("autoplay dispatch error: %s", e)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._queue):
            self._queue.pop(index)
            if index < self._current_index:
                self._current_index -= 1
            self._notify_change()

    def clear(self) -> None:
        self._queue.clear()
        self._history.clear()
        self._current_index = -1
        self._shuffle_order.clear()
        self._notify_change()

    def set_queue(self, songs: list[Song], start_index: int = 0) -> None:
        self._queue = list(songs)
        self._history.clear()
        self._current_index = start_index
        self._shuffle_order.clear()
        self._notify_change()

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    async def play_from(self, songs: list[Song], index: int = 0) -> None:
        """Replace the queue with `songs` and start playback at `index`,
        so the rest of the section auto-plays after the current track ends."""
        if not songs:
            return
        if index < 0 or index >= len(songs):
            index = 0
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        self._queue = list(songs)
        self._history.clear()
        self._shuffle_order.clear()
        self._current_index = index
        await self._play_current()
        self._notify_change()

    async def play_now(self, song: Song) -> None:
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        if song in self._queue:
            self._current_index = self._queue.index(song)
        else:
            self._queue.append(song)
            self._current_index = len(self._queue) - 1
        await self._play_current()
        self._notify_change()

    async def next(self) -> None:
        if self._repeat == RepeatMode.ONE:
            await self._play_current()
            return

        if self._shuffle:
            next_idx = self._next_shuffle_index()
        else:
            next_idx = self._current_index + 1

        if next_idx >= len(self._queue):
            if self._repeat == RepeatMode.ALL and self._queue:
                next_idx = 0
            else:
                self._player.stop()
                return

        if self.current_song:
            self._history.append(self.current_song)
        self._current_index = next_idx
        await self._play_current()
        self._notify_change()

    async def previous(self) -> None:
        if self._player.state.position > 3.0:
            self._player.seek(0)
            return
        if self._history:
            prev = self._history.pop()
            if prev in self._queue:
                self._current_index = self._queue.index(prev)
        elif self._current_index > 0:
            self._current_index -= 1
        await self._play_current()
        self._notify_change()

    async def _play_current(self) -> None:
        song = self.current_song
        if not song:
            logger.warning(
                "_play_current: no current song (index=%d, queue=%d)",
                self._current_index,
                len(self._queue),
            )
            return
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        logger.info("Resolving stream URL for %s (%s)", song.title, song.video_id)
        url = await self._api.get_stream_url(song.video_id)
        if url:
            logger.info("Got stream URL for %s — handing to MPV", song.video_id)
            self._player.play(url, song)
        else:
            logger.warning("No stream URL for %s — skipping", song.video_id)
            await self.next()

    # ------------------------------------------------------------------
    # Shuffle / Repeat — also pushed into PlayerState so the UI sees them
    # ------------------------------------------------------------------

    def toggle_shuffle(self) -> bool:
        self._shuffle = not self._shuffle
        self._shuffle_order.clear()
        self._sync_player_state()
        return self._shuffle

    def cycle_repeat(self) -> RepeatMode:
        modes = [RepeatMode.OFF, RepeatMode.ALL, RepeatMode.ONE]
        self._repeat = modes[(modes.index(self._repeat) + 1) % len(modes)]
        self._sync_player_state()
        return self._repeat

    def _sync_player_state(self) -> None:
        # Push shuffle/repeat into PlayerState so the PlayerBar reactives fire.
        # Guarded so unit tests with mocked players don't blow up here.
        try:
            with self._player._lock:  # noqa: SLF001
                self._player._state.shuffle = self._shuffle  # noqa: SLF001
                self._player._state.repeat = self._repeat  # noqa: SLF001
            self._player._notify_state()  # noqa: SLF001
        except AttributeError:
            pass

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> RepeatMode:
        return self._repeat

    def _next_shuffle_index(self) -> int:
        if not self._shuffle_order:
            indices = list(range(len(self._queue)))
            if self._current_index in indices:
                indices.remove(self._current_index)
            random.shuffle(indices)
            self._shuffle_order = indices
        return self._shuffle_order.pop(0) if self._shuffle_order else 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_song(self) -> Song | None:
        if 0 <= self._current_index < len(self._queue):
            return self._queue[self._current_index]
        return None

    @property
    def queue(self) -> list[Song]:
        return list(self._queue)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def history(self) -> list[Song]:
        return list(self._history)

    # ------------------------------------------------------------------
    # Track-end callback (called from MPV thread)
    # ------------------------------------------------------------------

    def _on_track_end(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug("Track-end fired but no running loop attached")
            return
        try:
            asyncio.run_coroutine_threadsafe(self.next(), loop)
        except Exception as e:
            logger.debug("Track-end dispatch error: %s", e)
