"""Multi-factor re-ranking of embedding search results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ytmuxiris.ai.models import AutoplayIntent
from ytmuxiris.utils.logger import get_logger

if TYPE_CHECKING:
    from ytmuxiris.models import Song

logger = get_logger(__name__)

# Heuristic: what energy level is associated with each mood keyword
_MOOD_TO_ENERGY: dict[str, str] = {
    "chill": "low",
    "relaxed": "low",
    "focus": "low",
    "ambient": "low",
    "sleep": "low",
    "lo-fi": "low",
    "lofi": "low",
    "energetic": "high",
    "pump-up": "high",
    "workout": "high",
    "dance": "high",
    "party": "high",
    "hype": "high",
    "intense": "high",
    "happy": "medium",
    "sad": "low",
    "emotional": "medium",
    "indie": "medium",
    "rock": "high",
    "pop": "medium",
    "jazz": "low",
    "classical": "low",
}


class Reranker:
    """Apply weighted scoring on top of embedding similarity.

    Final score formula (from the skill spec):
        0.5 × embedding_similarity
      + 0.2 × mood_match
      + 0.2 × energy_alignment
      + 0.1 × novelty_score
    """

    def rerank(
        self,
        candidates: list[tuple[Song, float]],
        intent: AutoplayIntent,
        already_played: set[str],
    ) -> list[Song]:
        scored: list[tuple[Song, float]] = []
        for song, sim in candidates:
            score = (
                0.5 * sim
                + 0.2 * self._mood_match(song, intent)
                + 0.2 * self._energy_alignment(intent)
                + 0.1 * self._novelty(song, already_played)
            )
            scored.append((song, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        seen: set[str] = set()
        result: list[Song] = []
        for song, _ in scored:
            vid = song.video_id
            if not vid:
                continue
            if intent.no_repeats and vid in already_played:
                continue
            if vid in seen:
                continue
            seen.add(vid)
            result.append(song)
        return result

    # ------------------------------------------------------------------
    # Scoring factors
    # ------------------------------------------------------------------

    def _mood_match(self, song: Song, intent: AutoplayIntent) -> float:
        if not intent.mood:
            return 0.5
        mood = intent.mood.lower()
        haystack = (f"{song.title} {song.artist} {song.album or ''}").lower()
        return 1.0 if mood in haystack else 0.2

    def _energy_alignment(self, intent: AutoplayIntent) -> float:
        """Score how well the intent's declared energy matches mood heuristics."""
        if not intent.mood:
            return 0.5
        expected = _MOOD_TO_ENERGY.get(intent.mood.lower(), "medium")
        return 1.0 if intent.energy == expected else 0.4

    def _novelty(self, song: Song, already_played: set[str]) -> float:
        return 0.0 if song.video_id in already_played else 1.0
