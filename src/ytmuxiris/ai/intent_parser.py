"""Parse natural language prompts into AutoplayIntent using a local Ollama LLM or Claude."""

from __future__ import annotations

import json
from typing import Any

from ytmuxiris.ai.models import AutoplayIntent, PlaybackContext
from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a music intent parser for a terminal music player.
Parse the user's music request into JSON with exactly these fields:
- mode: "radio" | "playlist" | "similar"
- mood: short mood string e.g. "chill", "energetic", "sad", "happy", "focus", "pump-up", ""
- energy: "low" | "medium" | "high"
- genres: list of genre strings
- seed_artists: list of artist names explicitly mentioned
- seed_query: a concise search query to find seed songs (required)
- no_repeats: boolean
- duration_hours: float, 0 means unlimited

Respond with valid JSON only. No explanation, no markdown."""


class IntentParser:
    """Parses free-form music prompts into structured AutoplayIntent.

    Uses Ollama by default; falls back to Claude if prefer_frontier=True and
    a Claude API key is configured.  A keyword-based rule engine handles the
    case where neither model is reachable.
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "gpt-oss:20b",
        claude_api_key: str | None = None,
        claude_model: str = "claude-haiku-4-5-20251001",
        prefer_frontier: bool = False,
    ) -> None:
        self._ollama_url = ollama_base_url.rstrip("/")
        self._ollama_model = ollama_model
        self._claude_api_key = claude_api_key
        self._claude_model = claude_model
        self._prefer_frontier = prefer_frontier

    async def parse(self, prompt: str, context: PlaybackContext) -> AutoplayIntent:
        full_prompt = self._inject_context(prompt, context)

        intent: AutoplayIntent | None = None
        if self._prefer_frontier and self._claude_api_key:
            intent = await self._parse_with_claude(full_prompt)
        if intent is None:
            intent = await self._parse_with_ollama(full_prompt)
        if intent is None:
            logger.info("LLM unavailable — using rule-based intent parser")
            intent = self._rule_based_fallback(prompt)

        intent.raw_prompt = prompt
        if not intent.seed_query:
            intent.seed_query = self._derive_query(prompt, intent)
        return intent

    # ------------------------------------------------------------------
    # Context injection
    # ------------------------------------------------------------------

    def _inject_context(self, prompt: str, context: PlaybackContext) -> str:
        if not context.current_song:
            return prompt
        song = context.current_song
        prefix = f"[Currently playing: {song.title} by {song.artist}] "
        return prefix + prompt

    # ------------------------------------------------------------------
    # LLM backends
    # ------------------------------------------------------------------

    async def _parse_with_ollama(self, prompt: str) -> AutoplayIntent | None:
        try:
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/chat",
                    json={
                        "model": self._ollama_model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                content = resp.json().get("message", {}).get("content", "{}")
                return self._parse_json(content)
        except Exception as e:
            logger.warning("Ollama intent parse failed: %s", e)
            return None

    async def _parse_with_claude(self, prompt: str) -> AutoplayIntent | None:
        try:
            import anthropic  # noqa: PLC0415

            client = anthropic.AsyncAnthropic(api_key=self._claude_api_key)
            msg = await client.messages.create(
                model=self._claude_model,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            content = msg.content[0].text if msg.content else "{}"
            return self._parse_json(content)
        except Exception as e:
            logger.warning("Claude intent parse failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # JSON → AutoplayIntent
    # ------------------------------------------------------------------

    def _parse_json(self, text: str) -> AutoplayIntent | None:
        try:
            text = text.strip()
            # Strip markdown code fences if present
            if "```" in text:
                for part in text.split("```"):
                    part = part.strip().lstrip("json").strip()
                    if part.startswith("{"):
                        text = part
                        break
            data: dict[str, Any] = json.loads(text)
            return AutoplayIntent(
                mode=str(data.get("mode", "radio")),
                mood=str(data.get("mood", "")),
                energy=str(data.get("energy", "medium")),
                genres=list(data.get("genres", [])),
                seed_artists=list(data.get("seed_artists", [])),
                seed_query=str(data.get("seed_query", "")),
                no_repeats=bool(data.get("no_repeats", True)),
                duration_hours=float(data.get("duration_hours", 0)),
            )
        except Exception as e:
            logger.warning("Failed to parse intent JSON (%s): %r", e, text[:120])
            return None

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _rule_based_fallback(self, prompt: str) -> AutoplayIntent:
        lower = prompt.lower()

        mood = ""
        energy = "medium"
        if any(
            w in lower for w in ["chill", "relax", "calm", "sleep", "study", "focus", "ambient"]
        ):
            mood = "chill"
            energy = "low"
        elif any(w in lower for w in ["workout", "pump", "hype", "dance", "party", "intense"]):
            mood = "energetic"
            energy = "high"
        elif any(w in lower for w in ["sad", "melancholy", "cry", "heartbreak", "emotional"]):
            mood = "sad"
            energy = "low"
        elif any(w in lower for w in ["happy", "upbeat", "fun", "positive", "joyful"]):
            mood = "happy"
            energy = "medium"

        return AutoplayIntent(mood=mood, energy=energy, seed_query=prompt[:60])

    def _derive_query(self, prompt: str, intent: AutoplayIntent) -> str:
        parts: list[str] = []
        if intent.seed_artists:
            parts.append(intent.seed_artists[0])
        if intent.genres:
            parts.append(intent.genres[0])
        if intent.mood:
            parts.append(intent.mood)
        return " ".join(parts) if parts else prompt[:60]
