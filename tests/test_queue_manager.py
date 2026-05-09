from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from ytmuxiris.models import Song
from ytmuxiris.player.audio_player import AudioPlayer, PlayerState, RepeatMode
from ytmuxiris.player.queue_manager import QueueManager


def _make_song(video_id: str, title: str = "T") -> Song:
    return Song(video_id=video_id, title=title, artist="A")


@pytest.fixture()
def player() -> MagicMock:
    p = MagicMock(spec=AudioPlayer)
    p.state = PlayerState()
    p.on_track_end = MagicMock()
    return p


@pytest.fixture()
def api() -> MagicMock:
    a = MagicMock()
    a.get_stream_url = AsyncMock(return_value="http://stream.url/audio")
    return a


@pytest.fixture()
def queue(player: MagicMock, api: MagicMock) -> QueueManager:
    return QueueManager(player, api)


class TestQueueBasics:
    def test_add(self, queue: QueueManager) -> None:
        s = _make_song("s1")
        queue.add(s)
        assert queue.queue == [s]

    def test_add_multiple(self, queue: QueueManager) -> None:
        songs = [_make_song(f"s{i}") for i in range(3)]
        queue.add_multiple(songs)
        assert len(queue.queue) == 3

    def test_clear(self, queue: QueueManager) -> None:
        queue.add(_make_song("s1"))
        queue.clear()
        assert queue.queue == []

    def test_remove(self, queue: QueueManager) -> None:
        s1, s2, s3 = (_make_song(f"s{i}") for i in range(3))
        queue.add_multiple([s1, s2, s3])
        queue.remove(1)
        assert queue.queue == [s1, s3]

    def test_set_queue(self, queue: QueueManager) -> None:
        songs = [_make_song(f"s{i}") for i in range(5)]
        queue.set_queue(songs, start_index=2)
        assert queue.current_index == 2


class TestPlayback:
    async def test_play_now_adds_if_not_present(
        self, queue: QueueManager, player: MagicMock
    ) -> None:
        s = _make_song("x1")
        await queue.play_now(s)
        assert s in queue.queue
        player.play.assert_called_once_with("http://stream.url/audio", s)

    async def test_play_now_uses_existing_index(
        self, queue: QueueManager, player: MagicMock
    ) -> None:
        songs = [_make_song(f"s{i}") for i in range(3)]
        queue.add_multiple(songs)
        await queue.play_now(songs[1])
        assert queue.current_index == 1

    async def test_next_advances(self, queue: QueueManager, player: MagicMock) -> None:
        songs = [_make_song(f"s{i}") for i in range(3)]
        queue.set_queue(songs, start_index=0)
        await queue.next()
        assert queue.current_index == 1

    async def test_next_stops_at_end_no_repeat(
        self, queue: QueueManager, player: MagicMock
    ) -> None:
        songs = [_make_song(f"s{i}") for i in range(2)]
        queue.set_queue(songs, start_index=1)
        await queue.next()
        player.stop.assert_called_once()

    async def test_previous_seeks_if_position_gt3(
        self, queue: QueueManager, player: MagicMock
    ) -> None:
        player.state = PlayerState(position=10.0)
        songs = [_make_song(f"s{i}") for i in range(3)]
        queue.set_queue(songs, start_index=2)
        await queue.previous()
        player.seek.assert_called_once_with(0)


class TestRepeatShuffle:
    def test_toggle_shuffle(self, queue: QueueManager) -> None:
        result = queue.toggle_shuffle()
        assert result is True
        result2 = queue.toggle_shuffle()
        assert result2 is False

    def test_cycle_repeat(self, queue: QueueManager) -> None:
        assert queue.cycle_repeat() == RepeatMode.ALL
        assert queue.cycle_repeat() == RepeatMode.ONE
        assert queue.cycle_repeat() == RepeatMode.OFF

    async def test_repeat_one_replays(self, queue: QueueManager, player: MagicMock) -> None:
        queue._repeat = RepeatMode.ONE
        s = _make_song("s1")
        queue.add(s)
        queue._current_index = 0
        await queue.next()
        # Should play current again
        player.play.assert_called_once()
