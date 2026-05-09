from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)

# TTL constants (seconds)
TTL_SEARCH = 5 * 60
TTL_LIBRARY = 30 * 60
TTL_STREAM_URL = 5 * 60 * 60
TTL_ARTIST = 60 * 60
TTL_ALBUM = 60 * 60


class APICache:
    """Two-level cache: in-memory dict + disk JSON files."""

    def __init__(self, cache_dir: str) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, tuple[Any, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, ttl: float) -> Any | None:
        """Return cached value if fresh, else None."""
        # Memory layer
        if key in self._mem:
            value, ts = self._mem[key]
            if time.time() - ts < ttl:
                return value
            del self._mem[key]

        # Disk layer
        path = self._path(key)
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age < ttl:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self._mem[key] = (data, time.time() - age)
                    return data
                except Exception as e:
                    logger.debug("Cache read error for %s: %s", key, e)
        return None

    def set(self, key: str, value: Any) -> None:
        """Store value in both memory and disk."""
        self._mem[key] = (value, time.time())
        path = self._path(key)
        try:
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.debug("Cache write error for %s: %s", key, e)

    def invalidate(self, key: str) -> None:
        self._mem.pop(key, None)
        path = self._path(key)
        if path.exists():
            path.unlink(missing_ok=True)

    def invalidate_library(self) -> None:
        """Clear all library-related cache entries."""
        for path in self._dir.glob("library_*.json"):
            path.unlink(missing_ok=True)
        self._mem = {k: v for k, v in self._mem.items() if not k.startswith("library_")}

    def invalidate_all(self) -> None:
        self._mem.clear()
        for path in self._dir.glob("*.json"):
            path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(prefix: str, **kwargs: Any) -> str:
        # Keep the prefix readable so invalidate_library() can match by
        # filename / dict-key prefix. Hash only the args portion to keep
        # the key length bounded.
        raw = json.dumps(kwargs, sort_keys=True)
        digest = hashlib.md5(raw.encode()).hexdigest()
        return f"{prefix}_{digest}"

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"
