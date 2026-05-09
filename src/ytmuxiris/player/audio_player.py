from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ytmuxiris.utils.logger import get_logger

if TYPE_CHECKING:
    from ytmuxiris.models import Song

logger = get_logger(__name__)


class RepeatMode(Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


@dataclass
class PlayerState:
    is_playing: bool = False
    is_paused: bool = False
    position: float = 0.0
    duration: float = 0.0
    volume: int = 80
    muted: bool = False
    shuffle: bool = False
    repeat: RepeatMode = RepeatMode.OFF
    current_song: Song | None = None


class AudioPlayer:
    """Thread-safe MPV-based audio player."""

    def __init__(self) -> None:
        self._mpv: object | None = None
        self._state = PlayerState()
        self._lock = threading.Lock()
        self._state_callbacks: list[Callable[[PlayerState], None]] = []
        self._track_end_callbacks: list[Callable[[], None]] = []
        self._available = False
        # Guard so a single track can't fire end-of-track twice (eof-reached
        # property + end-file event can both signal completion).
        self._last_ended_video_id: str | None = None
        # True between play(url) and the file-loaded event — so MPV's
        # idle-active observer doesn't misread the load gap as track-end.
        self._loading: bool = False
        self._init_mpv()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _init_mpv(self) -> None:
        try:
            import os
            import shutil
            import sys

            import mpv

            ytdl_path = (
                shutil.which("yt-dlp") or shutil.which("youtube-dl") or "/opt/homebrew/bin/yt-dlp"
            )
            # Make sure the lua hook can find the binary even if PATH was
            # stripped down by the launcher.
            os.environ["PATH"] = f"{os.path.dirname(ytdl_path)}:{os.environ.get('PATH', '')}"

            mpv_kwargs = dict(
                ytdl=True,
                video=False,
                terminal=False,
                input_default_bindings=False,
                input_vo_keyboard=False,
                audio_display=False,
                script_opts=(
                    f"ytdl_hook-ytdl_path={ytdl_path},"
                    "ytdl_hook-try_ytdl_first=yes,"
                    "ytdl_hook-exclude=storyboard"
                ),
                # android_vr returns direct progressive m4a/webm URLs (HTTP 200,
                # plain audio/mp4). Other clients either need cookies/PO tokens
                # or return HLS master playlists whose segments 403.
                ytdl_raw_options=(
                    "format=bestaudio[ext=m4a]/bestaudio,no-playlist=,"
                    "extractor-args=youtube:player_client=android_vr"
                ),
            )
            # On macOS, force CoreAudio so MPV actually opens an output device.
            # Without this, MPV sometimes silently falls back to the null AO
            # (timer advances, no sound).
            if sys.platform == "darwin":
                mpv_kwargs["ao"] = "coreaudio"

            # Capture MPV's own log so ytdl_hook errors land in our log file.
            def _mpv_log(loglevel: str, component: str, message: str) -> None:
                if loglevel in ("fatal", "error", "warn"):
                    logger.warning("MPV[%s/%s] %s", loglevel, component, message.rstrip())
                else:
                    logger.debug("MPV[%s/%s] %s", loglevel, component, message.rstrip())

            player = mpv.MPV(log_handler=_mpv_log, loglevel="warn", **mpv_kwargs)
            player["volume"] = 80
            player["mute"] = False
            # googlevideo's HLS segments 403 unless a real browser UA + Referer
            # are sent. ffmpeg's default UA is rejected.
            _ua = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.5 Safari/605.1.15"
            )
            player["user-agent"] = _ua
            player["referrer"] = "https://music.youtube.com/"
            # ffmpeg's HLS demuxer makes follow-up requests for each segment.
            # The top-level user-agent/referrer aren't always inherited by
            # those sub-requests, so set them via http-header-fields too.
            player["http-header-fields"] = (
                f"User-Agent: {_ua}\nReferer: https://music.youtube.com/\n"
                "Origin: https://music.youtube.com"
            )
            try:
                logger.info(
                    "MPV audio: ao=%s device=%s volume=%s mute=%s",
                    player.audio_out_params if hasattr(player, "audio_out_params") else "?",
                    player["audio-device"],
                    player["volume"],
                    player["mute"],
                )
            except Exception:
                pass

            @player.property_observer("pause")
            def on_pause(name: str, value: bool | None) -> None:  # noqa: ARG001
                with self._lock:
                    self._state.is_paused = bool(value)
                    self._state.is_playing = not bool(value)
                self._notify_state()

            @player.property_observer("eof-reached")
            def on_eof(name: str, value: bool | None) -> None:  # noqa: ARG001
                if value and self._state.current_song is not None:
                    logger.info("MPV eof-reached for %s", self._state.current_song.title)
                    self._handle_track_end()

            @player.property_observer("idle-active")
            def on_idle(name: str, value: bool | None) -> None:  # noqa: ARG001
                logger.debug("MPV idle-active=%s", value)
                # Fallback advance: some MPV/yt-dlp combos don't fire a clean
                # eof-reached or end-file=eof — but idle-active flipping True
                # after a track was loaded reliably means the file is over.
                # The video_id dedup in _handle_track_end keeps this from
                # double-firing when eof/end-file already triggered.
                if value and self._state.current_song is not None and not self._loading:
                    self._handle_track_end()

            @player.property_observer("core-idle")
            def on_core_idle(name: str, value: bool | None) -> None:  # noqa: ARG001
                logger.debug("MPV core-idle=%s", value)

            @player.event_callback("file-loaded")
            def on_file_loaded(event: object) -> None:  # noqa: ARG001
                with self._lock:
                    self._loading = False
                try:
                    logger.info(
                        "MPV file-loaded: ao=%s device=%s",
                        player["current-ao"],
                        player["audio-device"],
                    )
                except Exception:
                    pass

            @player.event_callback("end-file")
            def on_end_file(event: object) -> None:
                reason: object = None
                try:
                    d = event.as_dict() if hasattr(event, "as_dict") else {}  # type: ignore[attr-defined]
                    reason = d.get("reason")
                    file_error = d.get("file_error")
                    if isinstance(reason, bytes):
                        reason = reason.decode("utf-8", "replace")
                    if isinstance(file_error, bytes):
                        file_error = file_error.decode("utf-8", "replace")
                    logger.info("MPV end-file reason=%s file_error=%s", reason, file_error)
                except Exception as e:
                    logger.debug("end-file decode error: %s", e)
                # Reasons that mean "track is over and we should advance":
                # anything that is not an explicit stop/quit/redirect. This
                # is more lenient than allow-listing 'eof'/'error' because
                # python-mpv versions vary in how they decode the reason
                # (string vs int vs bytes), and an unknown reason after a
                # full playthrough still means "advance".
                _r = reason.decode("utf-8", "replace") if isinstance(reason, bytes) else reason
                _skip = {"stop", "quit", "redirect"}
                if _r not in _skip:
                    self._handle_track_end()

            @player.property_observer("time-pos")
            def on_time_pos(name: str, value: float | None) -> None:  # noqa: ARG001
                if value is not None:
                    with self._lock:
                        self._state.position = float(value)
                    self._notify_state()

            @player.property_observer("duration")
            def on_duration(name: str, value: float | None) -> None:  # noqa: ARG001
                if value is not None:
                    with self._lock:
                        self._state.duration = float(value)

            self._mpv = player
            self._available = True
            logger.info("MPV initialised")
        except Exception as e:
            logger.warning("MPV not available: %s — playback disabled", e)
            self._available = False

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------

    def play(self, url: str, song: Song) -> None:
        if not self._available or self._mpv is None:
            logger.warning("play() called but MPV is not available")
            return
        logger.info("MPV play: %s — %s (url len=%d)", song.title, song.artist, len(url or ""))
        with self._lock:
            self._state.current_song = song
            self._state.position = 0.0
            # New track: clear the end-of-track guard so its eof can fire.
            self._last_ended_video_id = None
            # Suppress idle-active false-positives during the load gap.
            self._loading = True
        try:
            self._mpv.play(url)  # type: ignore[attr-defined]
            self._mpv.pause = False  # type: ignore[attr-defined]
            self._mpv.mute = False  # type: ignore[attr-defined]
        except Exception as e:
            logger.error("MPV play failed: %s", e)
            return
        with self._lock:
            self._state.is_playing = True
            self._state.is_paused = False
        self._notify_state()

    def pause(self) -> None:
        if self._mpv:
            self._mpv.pause = True  # type: ignore[attr-defined]

    def resume(self) -> None:
        if self._mpv:
            self._mpv.pause = False  # type: ignore[attr-defined]

    def toggle(self) -> None:
        if self._state.is_paused:
            self.resume()
        else:
            self.pause()

    def stop(self) -> None:
        if self._mpv:
            self._mpv.stop()  # type: ignore[attr-defined]
        with self._lock:
            self._state.is_playing = False
            self._state.is_paused = False
            self._state.current_song = None
            self._state.position = 0.0

    def seek(self, seconds: float) -> None:
        if self._mpv:
            self._mpv.seek(seconds, reference="absolute")  # type: ignore[attr-defined]

    def seek_relative(self, delta: float) -> None:
        if self._mpv:
            self._mpv.seek(delta, reference="relative")  # type: ignore[attr-defined]

    def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, volume))
        if self._mpv:
            self._mpv.volume = volume  # type: ignore[attr-defined]
        with self._lock:
            self._state.volume = volume
        self._notify_state()

    def toggle_mute(self) -> None:
        if self._mpv:
            self._mpv.mute = not self._mpv.mute  # type: ignore[attr-defined]
        with self._lock:
            self._state.muted = not self._state.muted
        self._notify_state()

    def terminate(self) -> None:
        if self._mpv:
            try:
                self._mpv.terminate()  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # State & callbacks
    # ------------------------------------------------------------------

    @property
    def state(self) -> PlayerState:
        with self._lock:
            return PlayerState(
                is_playing=self._state.is_playing,
                is_paused=self._state.is_paused,
                position=self._state.position,
                duration=self._state.duration,
                volume=self._state.volume,
                muted=self._state.muted,
                shuffle=self._state.shuffle,
                repeat=self._state.repeat,
                current_song=self._state.current_song,
            )

    def on_state_change(self, cb: Callable[[PlayerState], None]) -> None:
        self._state_callbacks.append(cb)

    def on_track_end(self, cb: Callable[[], None]) -> None:
        self._track_end_callbacks.append(cb)

    def _notify_state(self) -> None:
        state = self.state
        for cb in self._state_callbacks:
            try:
                cb(state)
            except Exception as e:
                logger.debug("State callback error: %s", e)

    def _handle_track_end(self) -> None:
        # Dedup: eof-reached property + end-file event can both fire for the
        # same track. Only advance once per track.
        with self._lock:
            song = self._state.current_song
            vid = song.video_id if song is not None else None
            if vid is not None and self._last_ended_video_id == vid:
                return
            self._last_ended_video_id = vid
        for cb in self._track_end_callbacks:
            try:
                cb()
            except Exception as e:
                logger.debug("Track-end callback error: %s", e)
