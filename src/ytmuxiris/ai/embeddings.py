"""Embedding engine — converts songs and prompts to vectors for semantic similarity search."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

from ytmuxiris.utils.logger import get_logger

if TYPE_CHECKING:
    from ytmuxiris.models import Song

logger = get_logger(__name__)

_DEFAULT_EMBED_MODEL = "nomic-embed-text"


class EmbeddingEngine:
    """Compute dense embeddings via Ollama and compare by cosine similarity.

    Embeddings are cached on disk so songs are only embedded once.
    Falls back to zero-vector (no-op similarity) if Ollama is unreachable.
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = _DEFAULT_EMBED_MODEL,
        cache_dir: Path | None = None,
    ) -> None:
        self._url = ollama_base_url.rstrip("/")
        self._model = model
        self._mem: dict[str, list[float]] = {}
        self._cache_path = (cache_dir / "embeddings_cache.json") if cache_dir else None
        self._dirty = False
        self._load_cache()

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        if self._cache_path and self._cache_path.exists():
            try:
                with self._cache_path.open() as f:
                    self._mem = json.load(f)
                logger.debug("Loaded %d cached embeddings", len(self._mem))
            except Exception as e:
                logger.warning("Failed to load embedding cache: %s", e)
                self._mem = {}

    def _flush_cache(self) -> None:
        if not self._dirty or not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_path.open("w") as f:
                json.dump(self._mem, f)
            self._dirty = False
        except Exception as e:
            logger.warning("Failed to save embedding cache: %s", e)

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float] | None:
        if text in self._mem:
            return self._mem[text]
        vec = await self._embed_via_ollama(text)
        if vec:
            self._mem[text] = vec
            self._dirty = True
            self._flush_cache()
        return vec

    async def _embed_via_ollama(self, text: str) -> list[float] | None:
        try:
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json().get("embedding")
        except Exception as e:
            logger.debug("Ollama embed failed for %r: %s", text[:40], e)
            return None

    async def embed_song(self, song: Song) -> list[float] | None:
        parts = [f"{song.title} by {song.artist}"]
        if song.album:
            parts.append(f"from {song.album}")
        return await self.embed(" ".join(parts))

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    async def find_similar(
        self,
        query_text: str,
        songs: list[Song],
        top_k: int = 30,
    ) -> list[tuple[Song, float]]:
        """Return (song, cosine_similarity) pairs sorted descending."""
        query_vec = await self.embed(query_text)

        results: list[tuple[Song, float]] = []
        for song in songs:
            if query_vec:
                song_vec = await self.embed_song(song)
                sim = self.cosine_similarity(query_vec, song_vec) if song_vec else 0.0
            else:
                sim = 0.0
            results.append((song, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Math
    # ------------------------------------------------------------------

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)
