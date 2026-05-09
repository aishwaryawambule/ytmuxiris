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
| `a` | AI Autoplay |
| `?` | Help |
| `q` | Quit |

## AI Autoplay

Press `a` (or pick "AI Autoplay" in the sidebar), type something like *"lo-fi for late-night coding"* or *"upbeat 90s alt-rock, no repeats"*, and ytmuxiris builds a queue that matches and saves it back to your account as `Autoplay: <prompt>`.

### Why it exists

YouTube Music's own radio is anchored to a single seed song or artist. That works when you already know what you want to hear, but it falls apart for *vibe-shaped* requests — energy level, time of day, genre blends, "more like what's playing but darker", and so on. The autoplay engine fills that gap by treating a free-form prompt as the seed instead.

### How it works

The pipeline lives in `src/ytmuxiris/ai/` and runs entirely client-side:

1. **Intent parsing** (`intent_parser.py`) — turns the prompt into a structured `AutoplayIntent` (mood, energy, genres, seed artists, search query, mode).
2. **Candidate retrieval** — runs the seed query through the YouTube Music search and watch-playlist endpoints to gather a candidate pool.
3. **Embedding & similarity** (`embeddings.py`) — embeds the prompt and each candidate's title/artist/album metadata, then ranks by cosine similarity. Embeddings are cached on disk so re-prompts are cheap.
4. **Re-ranking** (`reranker.py`) — boosts/penalises candidates against the parsed intent (matching mood, requested energy, seed artists; demoting near-duplicates and items that violate `no_repeats`).
5. **Queueing** — top tracks are pushed to the queue and persisted as a YouTube Music playlist so the result survives across sessions.

### Model choices

ytmuxiris is **local-first** for privacy and cost: by default it talks to a local [Ollama](https://ollama.ai/) instance for both the intent LLM and the embedding model. If Ollama isn't reachable, a keyword rule engine handles intent parsing so the feature degrades gracefully rather than failing.

A frontier model (Anthropic Claude) is opt-in for users who want sharper intent parsing on ambiguous prompts. Toggle it in Settings (`use_frontier_model`) and provide a `claude_api_key` — `claude-haiku-4-5` is the default since it's fast and cheap for this short structured-JSON task.

Configure under `~/.config/ytmuxiris/config.yaml`:

```yaml
ollama_url: http://localhost:11434
ollama_model: gpt-oss:20b           # for intent parsing
embed_model: nomic-embed-text       # for similarity
use_frontier_model: false
claude_api_key: ""
claude_model: claude-haiku-4-5-20251001
```

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
├── ai/                 — Autoplay engine: intent parser, embeddings, reranker
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
