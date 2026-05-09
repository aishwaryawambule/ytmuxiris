from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ytmuxiris.models import Song


@dataclass
class AutoplayIntent:
    """Parsed intent from a natural language autoplay prompt."""

    mode: str = "radio"  # radio | playlist | similar
    mood: str = ""
    energy: str = "medium"  # low | medium | high
    genres: list[str] = field(default_factory=list)
    seed_artists: list[str] = field(default_factory=list)
    seed_query: str = ""
    no_repeats: bool = True
    duration_hours: float = 0.0
    raw_prompt: str = ""

    def __repr__(self) -> str:
        return (
            f"AutoplayIntent(mood={self.mood!r}, energy={self.energy!r}, "
            f"query={self.seed_query!r}, artists={self.seed_artists})"
        )


@dataclass
class PlaybackContext:
    """Current TUI state used to resolve ambiguous prompts like 'this music'."""

    current_song: Song | None = None
    queue_songs: list[Song] = field(default_factory=list)
    recent_history: list[Song] = field(default_factory=list)
    last_prompt: str = ""
    last_intent: AutoplayIntent | None = None
