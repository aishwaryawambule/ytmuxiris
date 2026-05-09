"""Tests for the AI autoplay pipeline."""

from __future__ import annotations

import pytest
from ytmuxiris.ai.autoplay_engine import AutoplayEngine
from ytmuxiris.ai.embeddings import EmbeddingEngine
from ytmuxiris.ai.intent_parser import IntentParser
from ytmuxiris.ai.models import AutoplayIntent, PlaybackContext
from ytmuxiris.ai.reranker import Reranker
from ytmuxiris.models import Song

# ---------------------------------------------------------------------------
# IntentParser — rule-based fallback (no LLM needed)
# ---------------------------------------------------------------------------


class TestIntentParser:
    def setup_method(self) -> None:
        self.parser = IntentParser()

    def test_chill_keywords_detected(self) -> None:
        intent = self.parser._rule_based_fallback("chill music for studying")
        assert intent.mood == "chill"
        assert intent.energy == "low"

    def test_energetic_keywords_detected(self) -> None:
        intent = self.parser._rule_based_fallback("pump up workout tracks")
        assert intent.mood == "energetic"
        assert intent.energy == "high"

    def test_sad_keywords_detected(self) -> None:
        intent = self.parser._rule_based_fallback("sad melancholy songs")
        assert intent.mood == "sad"
        assert intent.energy == "low"

    def test_happy_keywords_detected(self) -> None:
        intent = self.parser._rule_based_fallback("upbeat happy pop")
        assert intent.mood == "happy"
        assert intent.energy == "medium"

    def test_no_keywords_neutral(self) -> None:
        intent = self.parser._rule_based_fallback("radiohead songs")
        assert intent.mood == ""
        assert intent.energy == "medium"

    def test_seed_query_set(self) -> None:
        intent = self.parser._rule_based_fallback("jazz piano")
        assert "jazz piano" in intent.seed_query

    def test_json_parse_valid(self) -> None:
        json_str = (
            '{"mode": "radio", "mood": "chill", "energy": "low", '
            '"genres": ["lo-fi"], "seed_artists": [], '
            '"seed_query": "lo-fi hip hop", "no_repeats": true, "duration_hours": 0}'
        )
        intent = self.parser._parse_json(json_str)
        assert intent is not None
        assert intent.mood == "chill"
        assert intent.seed_query == "lo-fi hip hop"
        assert intent.genres == ["lo-fi"]

    def test_json_parse_with_markdown_fence(self) -> None:
        text = '```json\n{"mood": "focus", "energy": "low", "seed_query": "ambient"}\n```'
        intent = self.parser._parse_json(text)
        assert intent is not None
        assert intent.mood == "focus"

    def test_json_parse_invalid_returns_none(self) -> None:
        assert self.parser._parse_json("not json at all") is None

    def test_derive_query_from_artist(self) -> None:
        intent = AutoplayIntent(seed_artists=["Radiohead"], mood="indie")
        q = self.parser._derive_query("play radiohead", intent)
        assert "Radiohead" in q

    def test_context_injection(self) -> None:
        song = Song(video_id="x", title="Creep", artist="Radiohead")
        ctx = PlaybackContext(current_song=song)
        result = self.parser._inject_context("more like this", ctx)
        assert "Creep" in result
        assert "Radiohead" in result

    @pytest.mark.asyncio
    async def test_parse_falls_back_to_rules_when_ollama_down(self) -> None:
        # Uses a non-existent Ollama URL → falls through to rule-based
        parser = IntentParser(ollama_base_url="http://localhost:19999")
        ctx = PlaybackContext()
        intent = await parser.parse("chill lo-fi for focus", ctx)
        assert intent.mood == "chill"
        assert intent.energy == "low"
        assert intent.raw_prompt == "chill lo-fi for focus"


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


class TestReranker:
    def setup_method(self) -> None:
        self.reranker = Reranker()

    def _make_songs(self) -> list[Song]:
        return [
            Song(video_id="a", title="Chill Beats", artist="Lofi Artist"),
            Song(video_id="b", title="Workout Pump", artist="DJ Energy"),
            Song(video_id="c", title="Focus Session", artist="Ambient"),
            Song(video_id="d", title="Night Drive", artist="Indie Band"),
        ]

    def test_chill_intent_ranks_chill_song_higher(self) -> None:
        songs = self._make_songs()
        intent = AutoplayIntent(mood="chill", energy="low")
        candidates = [(s, 0.5) for s in songs]
        result = self.reranker.rerank(candidates, intent, set())
        assert result[0].video_id == "a"

    def test_no_repeats_filters_played(self) -> None:
        songs = self._make_songs()
        intent = AutoplayIntent(no_repeats=True)
        candidates = [(s, 0.8) for s in songs]
        already_played = {"a", "b"}
        result = self.reranker.rerank(candidates, intent, already_played)
        ids = [s.video_id for s in result]
        assert "a" not in ids
        assert "b" not in ids

    def test_deduplication(self) -> None:
        song = Song(video_id="x", title="Track", artist="Artist")
        candidates = [(song, 0.9), (song, 0.8)]
        result = self.reranker.rerank(candidates, AutoplayIntent(), set())
        assert len(result) == 1

    def test_empty_candidates(self) -> None:
        result = self.reranker.rerank([], AutoplayIntent(), set())
        assert result == []


# ---------------------------------------------------------------------------
# EmbeddingEngine — offline math
# ---------------------------------------------------------------------------


class TestEmbeddingEngine:
    def test_cosine_similarity_identical(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert EmbeddingEngine.cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert EmbeddingEngine.cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_similarity_zero_vector(self) -> None:
        assert EmbeddingEngine.cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    @pytest.mark.asyncio
    async def test_find_similar_no_ollama_returns_zero_scores(self) -> None:
        engine = EmbeddingEngine(ollama_base_url="http://localhost:19999")
        songs = [
            Song(video_id="a", title="Track A", artist="Artist"),
            Song(video_id="b", title="Track B", artist="Other"),
        ]
        pairs = await engine.find_similar("chill music", songs)
        assert len(pairs) == 2
        assert all(score == 0.0 for _, score in pairs)


# ---------------------------------------------------------------------------
# AutoplayEngine — context resolution
# ---------------------------------------------------------------------------


class TestAutoplayEngine:
    def _make_engine(self) -> AutoplayEngine:
        from unittest.mock import MagicMock

        return AutoplayEngine(
            api=MagicMock(),
            intent_parser=MagicMock(),
            embedding_engine=MagicMock(),
            reranker=Reranker(),
        )

    def test_resolve_context_phrase(self) -> None:
        engine = self._make_engine()
        engine._context.current_song = Song(video_id="x", title="Creep", artist="Radiohead")
        resolved = engine._resolve_context_references("play more like this")
        assert "Creep" in resolved
        assert "Radiohead" in resolved

    def test_resolve_no_context_unchanged(self) -> None:
        engine = self._make_engine()
        prompt = "play radiohead songs"
        assert engine._resolve_context_references(prompt) == prompt

    def test_deduplicate_removes_duplicates(self) -> None:
        engine = self._make_engine()
        song = Song(video_id="a", title="T", artist="A")
        result = engine._deduplicate([song, song, song])
        assert len(result) == 1

    def test_build_queue_artist_diversity(self) -> None:
        engine = self._make_engine()
        intent = AutoplayIntent()
        # 5 songs from same artist
        same_artist = [Song(video_id=str(i), title=f"T{i}", artist="BigArtist") for i in range(5)]
        candidates = [(s, 0.9) for s in same_artist]
        queue = engine._build_queue(candidates, intent)
        artist_songs = [s for s in queue if s.artist == "BigArtist"]
        assert len(artist_songs) <= 3

    def test_update_context(self) -> None:
        engine = self._make_engine()
        song = Song(video_id="s1", title="T", artist="A")
        history = [Song(video_id="h1", title="H", artist="A")]
        engine.update_context(current_song=song, history=history)
        assert engine._context.current_song == song
        assert "h1" in engine._played_ids
