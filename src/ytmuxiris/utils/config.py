from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)

CONFIG_DIR = Path(os.path.expanduser("~/.config/ytmuxiris"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    audio_quality: str = "high"  # low | medium | high
    volume: int = 80
    shuffle: bool = False
    repeat: str = "off"  # off | one | all
    theme: str = "dark"
    keybindings_file: str = str(CONFIG_DIR / "keybindings.json")
    cache_dir: str = str(CONFIG_DIR / "cache")
    auth_file: str = str(CONFIG_DIR / "oauth.json")
    max_search_results: int = 20
    library_limit: int = 100
    extra: dict[str, Any] = field(default_factory=dict)


def load_config() -> Config:
    """Load config from YAML file, creating defaults if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        _write_defaults()

    try:
        with CONFIG_FILE.open() as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load config: %s — using defaults", e)
        data = {}

    cfg = Config()
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
        else:
            cfg.extra[key] = value
    return cfg


_SENSITIVE_KEYS = {"oauth_client_id", "oauth_client_secret"}


def save_config(config: Config) -> None:
    """Persist config back to YAML, never writing OAuth credentials."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {k: v for k, v in config.__dict__.items() if k != "extra"}
    data.update({k: v for k, v in config.extra.items() if k not in _SENSITIVE_KEYS})
    try:
        with CONFIG_FILE.open("w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)
    except Exception as e:
        logger.error("Failed to save config: %s", e)


def _write_defaults() -> None:
    defaults = Config()
    save_config(defaults)
