"""Main AI autoplay engine — orchestrates: intent → search → embed → rerank → queue."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ytmuxiris.ai.embeddings import EmbeddingEngine
from ytmuxiris.ai.intent_parser import IntentParser
from ytmuxiris.ai.models import AutoplayIntent, PlaybackContext
from ytmuxiris.ai.reranker import Reranker
from ytmuxiris.utils.logger import get_logger

if TYPE_CHECKING:
    from ytmuxiris.api import YouTubeMusicAPI
    from ytmuxiris.models import Song

logger = get_logger(__name__)

StatusCallback = Callable[[str], None]

_QUEUE_SIZE = 25
_SEARCH_LIMIT = 40

# Phrases that refer to the currently playing song
_CONTEXT_PHRASES = (
    "this music",
    "this song",
    "like this",
    "same vibe",
    "more of this",
    "similar to this",
    "more like this",
)


class AutoplayEngine:
    """Orchestrates AI-driven autoplay from a natural language prompt.

    Pipeline:
      1. Resolve context references ("this music", "same vibe")
      2. Parse intent (LLM)
      3. Gather candidate songs (search + radio)
      4. Semantic re-ranking (embeddings + weighted scoring)
      5. Diversity-constrained queue construction
    """

    def __init__(
        self,
        api: YouTubeMusicAPI,
        intent_parser: IntentParser,
        embedding_engine: EmbeddingEngine,
        reranker: Reranker,
    ) -> None:
        self._api = api
        self._intent_parser = intent_parser
        self._embedder = embedding_engine
        self._reranker = reranker
        self._context = PlaybackContext()
        self._played_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def update_context(
        self,
        current_song: Song | None = None,
        queue_songs: list[Song] | None = None,
        history: list[Song] | None = None,
    ) -> None:
        if current_song is not None:
            self._context.current_song = current_song
        if queue_songs is not None:
            self._context.queue_songs = queue_songs
        if history is not None:
            self._context.recent_history = history
            self._played_ids = {s.video_id for s in history if s.video_id}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        prompt: str,
        on_status: StatusCallback | None = None,
    ) -> list[Song]:
        def status(msg: str) -> None:
            logger.info("Autoplay: %s", msg)
            if on_status:
                on_status(msg)

        resolved = self._resolve_context_references(prompt)

        status("Parsing intent…")
        intent = await self._intent_parser.parse(resolved, self._context)
        self._context.last_intent = intent
        self._context.last_prompt = prompt
        logger.info("Parsed intent: %s", intent)

        status(f"Searching for '{intent.seed_query}'…")
        candidates = await self._gather_candidates(intent)
        if not candidates:
            # Last-resort fallback: search with the raw user prompt directly so
            # we never silently return an empty queue when the LLM fails or the
            # parsed intent is too narrow.
            status("Retrying with the raw prompt…")
            candidates = await self._api.search_songs(
                prompt[:60] or resolved[:60], limit=_SEARCH_LIMIT
            )
            candidates = self._deduplicate(candidates)
        if not candidates:
            status("No songs found — try a different prompt.")
            return []

        status(f"Ranking {len(candidates)} songs…")
        ranked = await self._rank(candidates, intent, resolved)

        status("Building queue…")
        queue = self._build_queue(ranked, intent)

        status(f"Done — {len(queue)} songs queued.")
        return queue

    # ------------------------------------------------------------------
    # Step 1: context resolution
    # ------------------------------------------------------------------

    def _resolve_context_references(self, prompt: str) -> str:
        lower = prompt.lower()
        song = self._context.current_song
        if not song:
            return prompt
        seed = f"{song.title} {song.artist}"
        for phrase in _CONTEXT_PHRASES:
            if phrase in lower:
                prompt = prompt.lower().replace(phrase, f"music like {seed}", 1)
                break
        return prompt

    # ------------------------------------------------------------------
    # Step 2: candidate gathering
    # ------------------------------------------------------------------

    async def _gather_candidates(self, intent: AutoplayIntent) -> list[Song]:
        songs: list[Song] = []

        if intent.seed_query:
            found = await self._api.search_songs(intent.seed_query, limit=_SEARCH_LIMIT)
            songs.extend(found)

        for artist in intent.seed_artists[:2]:
            found = await self._api.search_songs(artist, limit=20)
            songs.extend(found)

        if self._context.current_song:
            radio = await self._api.get_song_radio(self._context.current_song.video_id)
            songs.extend(radio)

        if intent.mood and len(songs) < 20:
            mood_songs = await self._api.search_songs(f"{intent.mood} music", limit=20)
            songs.extend(mood_songs)

        return self._deduplicate(songs)

    @staticmethod
    def _deduplicate(songs: list[Song]) -> list[Song]:
        seen: set[str] = set()
        result: list[Song] = []
        for s in songs:
            if s.video_id and s.video_id not in seen:
                seen.add(s.video_id)
                result.append(s)
        return result

    # ------------------------------------------------------------------
    # Step 3: semantic ranking
    # ------------------------------------------------------------------

    async def _rank(
        self,
        candidates: list[Song],
        intent: AutoplayIntent,
        prompt: str,
    ) -> list[tuple[Song, float]]:
        query_parts = [intent.mood, intent.seed_query] + intent.genres
        query_text = " ".join(p for p in query_parts if p).strip() or prompt
        return await self._embedder.find_similar(query_text, candidates, top_k=len(candidates))

    # ------------------------------------------------------------------
    # Step 4: queue construction with diversity constraints
    # ------------------------------------------------------------------

    def _build_queue(
        self,
        ranked: list[tuple[Song, float]],
        intent: AutoplayIntent,
    ) -> list[Song]:
        songs = self._reranker.rerank(ranked, intent, self._played_ids)

        # No more than 3 songs from the same artist in the first 20 slots
        artist_count: dict[str, int] = {}
        queue: list[Song] = []
        for song in songs:
            count = artist_count.get(song.artist, 0)
            if count < 3:
                queue.append(song)
                artist_count[song.artist] = count + 1
            if len(queue) >= _QUEUE_SIZE:
                break

        return queue
