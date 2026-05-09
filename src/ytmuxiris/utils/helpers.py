from __future__ import annotations


def format_duration(seconds: int) -> str:
    """Convert seconds to MM:SS or H:MM:SS string."""
    if seconds <= 0:
        return "0:00"
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def truncate_text(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to max_len characters, appending suffix if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def parse_duration(duration: object) -> int:
    """Convert duration to total seconds.

    Accepts an int/float (seconds), a numeric string ("225"), or a colon
    formatted string ("M:SS" / "H:MM:SS"). Returns 0 for anything else.
    """
    if duration is None:
        return 0
    if isinstance(duration, int | float):
        return max(0, int(duration))
    if not isinstance(duration, str):
        return 0
    s = duration.strip()
    if not s:
        return 0
    if ":" not in s:
        try:
            return max(0, int(float(s)))
        except ValueError:
            return 0
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0
