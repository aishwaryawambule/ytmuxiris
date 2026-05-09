# ytmuxiris — A Goo Goo Dolls-inspired TUI for YouTube Music.

A terminal UI for YouTube Music built with [Textual](https://textual.textualize.io/), `ytmusicapi`, and `python-mpv`. Minimalist. Fast. Keyboard-centric.

## Requirements

- Python 3.11+
- [mpv](https://mpv.io/) (`brew install mpv` on macOS, `apt install mpv` on Debian/Ubuntu)
- A logged-in browser session at [music.youtube.com](https://music.youtube.com) (Chrome, Firefox, Brave, or Edge)

## Install

The recommended installer is [`pipx`](https://pipx.pypa.io/), which keeps the app isolated from your system Python.

```bash
# Install pipx if you don't have it
brew install pipx                                   # macOS
# or: python3 -m pip install --user pipx && python3 -m pipx ensurepath

# Install ytmuxiris from a local clone
git clone https://github.com/<your-user>/ytmuxiris.git
cd ytmuxiris
pipx install .

# Or install directly from GitHub
pipx install git+https://github.com/<your-user>/ytmuxiris.git
```

Once installed, run it from anywhere:

```bash
ytmuxiris
```

### Alternative: install from a built wheel

```bash
# Build the wheel (requires Poetry)
poetry build

# Install it with pipx
pipx install dist/ytmuxiris-0.1.0-py3-none-any.whl
```

### Upgrade / uninstall

```bash
pipx upgrade ytmuxiris
pipx uninstall ytmuxiris
```

## Authentication

No credentials, no Google Cloud setup, no API keys.

ytmuxiris imports your existing browser session using [yt-dlp](https://github.com/yt-dlp/yt-dlp)'s cookie extraction. Just be logged in to [music.youtube.com](https://music.youtube.com), then:

```bash
ytmuxiris
# → Click "Import from Browser" on the login screen
# → Done — your browser session is imported automatically
```

The session is saved to `~/.config/ytmuxiris/auth.json` (permissions 600). **Sign out** (Settings → Sign out) deletes it and wipes all cached data.

## Keybindings

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `n` | Next track |
| `p` | Previous track |
| `s` | Toggle shuffle |
| `r` | Cycle repeat (off → all → one) |
| `m` | Toggle mute |
| `+` / `-` | Volume up / down |
| `,` / `.` | Seek -10s / +10s |
| `1`–`4` | Home / Search / Library / Queue |
| `/` | Focus search |
| `?` | Help |
| `q` | Quit |

## Development

The project uses [Poetry](https://python-poetry.org/) for development.

```bash
# Install dependencies (including dev tools)
poetry install

# Run from source
poetry run ytmuxiris

# Tests
poetry run pytest

# Lint / type check / format
poetry run ruff check src tests
poetry run mypy src
poetry run ruff format src tests

# Build distributables
poetry build         # creates dist/ytmuxiris-*.whl and *.tar.gz
```

## Architecture

```
src/ytmuxiris/
├── app.py              — Root App, bindings, screen stack, reactives
├── main.py             — Entry point (exposed as the `ytmuxiris` console script)
├── api/                — ytmusicapi wrapper (typed, cached, async)
├── player/             — MPV audio player + queue manager
├── models/             — Song, Album, Artist, Playlist dataclasses
├── ui/
│   ├── screens/        — Home, Search, Library, Playlist, Queue, Settings, Login, Help
│   ├── widgets/        — PlayerBar, Sidebar, SongList, SearchBar, AlbumGrid, …
│   └── styles/         — main.tcss (all CSS)
└── utils/              — Config, cache, logger, helpers
```

User data lives under `~/.config/ytmuxiris/`:
- `auth.json` — imported browser session
- `config.yaml` — user settings
- `cache/` — disk cache (search results, library, stream URLs)
- `logs/` — application logs

## License

MIT
