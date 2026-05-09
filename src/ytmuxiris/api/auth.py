from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from ytmuxiris.utils.logger import get_logger

logger = get_logger(__name__)


class AuthManager:
    """Manages ytmusicapi OAuth and browser-header authentication."""

    def __init__(self, config_dir: str = "~/.config/ytmuxiris") -> None:
        self._config_dir = Path(os.path.expanduser(config_dir))
        self._config_dir.mkdir(parents=True, exist_ok=True)
        # OAuth token (preferred when the Google client is of type "TV and
        # Limited Input devices"; otherwise YouTube Music returns HTTP 400).
        self.auth_file = str(self._config_dir / "oauth.json")
        # Browser-headers fallback (works without OAuth client setup).
        self.headers_file = str(self._config_dir / "auth.json")
        self._secrets_file = self._config_dir / ".secrets"
        self.last_error: str | None = None

    def _active_auth_file(self) -> str | None:
        """Pick whichever credential file exists, preferring browser headers
        because the user's OAuth client commonly returns HTTP 400."""
        if Path(self.headers_file).exists():
            return self.headers_file
        if Path(self.auth_file).exists():
            return self.auth_file
        return None

    def is_authenticated(self) -> bool:
        return self._active_auth_file() is not None

    def _load_oauth_credentials(self) -> tuple[str | None, str | None]:
        """Read YTMUSICAPI_CLIENT_ID/SECRET from env then ~/.config/ytmuxiris/.secrets."""
        client_id = os.environ.get("YTMUSICAPI_CLIENT_ID")
        client_secret = os.environ.get("YTMUSICAPI_CLIENT_SECRET")
        if client_id and client_secret:
            return client_id, client_secret

        if self._secrets_file.exists():
            try:
                for line in self._secrets_file.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key == "YTMUSICAPI_CLIENT_ID" and not client_id:
                        client_id = value
                    elif key == "YTMUSICAPI_CLIENT_SECRET" and not client_secret:
                        client_secret = value
            except Exception as e:
                logger.error("Failed to read .secrets: %s", e)

        return client_id, client_secret

    def setup_oauth(self, status_cb: Callable[[str], None] | None = None) -> bool:
        """OAuth device flow — uses ytmusicapi.setup_oauth with stored credentials."""

        def _status(msg: str) -> None:
            if status_cb is not None:
                try:
                    status_cb(msg)
                except Exception as e:
                    logger.debug("status_cb error: %s", e)

        client_id, client_secret = self._load_oauth_credentials()
        if not client_id or not client_secret:
            msg = (
                "Missing YTMUSICAPI_CLIENT_ID/SECRET — set env vars or "
                f"populate {self._secrets_file}"
            )
            logger.error(msg)
            self.last_error = msg
            _status(msg)
            return False

        try:
            from ytmusicapi import setup_oauth as _setup_oauth

            _status("Opening browser for OAuth…")
            _setup_oauth(
                client_id=client_id,
                client_secret=client_secret,
                filepath=self.auth_file,
                open_browser=True,
            )
            logger.info("OAuth setup complete")
            self.last_error = None
            _status("Authenticated.")
            return True
        except Exception as e:
            logger.error("OAuth setup failed: %s", e)
            self.last_error = str(e)
            _status(f"OAuth failed: {e}")
            return False

    def setup_from_browser_cookies(self, status_cb: Callable[[str], None] | None = None) -> bool:
        """Extract YouTube Music cookies from a local browser via yt-dlp and
        persist them as ytmusicapi browser-header auth. No OAuth client setup
        required."""

        def _status(msg: str) -> None:
            if status_cb is not None:
                try:
                    status_cb(msg)
                except Exception as e:
                    logger.debug("status_cb error: %s", e)

        try:
            from yt_dlp.cookies import extract_cookies_from_browser
        except Exception as e:
            msg = f"yt-dlp not available: {e}"
            logger.error(msg)
            self.last_error = msg
            _status(msg)
            return False

        class _SilentLogger:
            def debug(self, *_a: object, **_kw: object) -> None:
                pass

            def info(self, *_a: object, **_kw: object) -> None:
                pass

            def warning(self, *_a: object, **_kw: object) -> None:
                pass

            def error(self, *_a: object, **_kw: object) -> None:
                pass

        last_exc: str | None = None
        for browser in ("chrome", "firefox", "brave", "edge", "chromium", "safari"):
            try:
                _status(f"Reading cookies from {browser}…")
                jar = extract_cookies_from_browser(browser, logger=_SilentLogger())
            except Exception as e:
                last_exc = f"{browser}: {e}"
                logger.debug("Cookie extract failed for %s: %s", browser, e)
                continue

            yt_cookies: dict[str, str] = {}
            required = ("SAPISID", "__Secure-3PAPISID")
            for cookie in jar:
                if not cookie.domain or "youtube.com" not in cookie.domain:
                    continue
                # Last write wins; that's fine — duplicates across subdomains
                # carry the same value.
                yt_cookies[cookie.name] = cookie.value or ""

            if not any(name in yt_cookies for name in required):
                logger.debug("Browser %s has no SAPISID cookie", browser)
                continue

            cookie_header = "; ".join(f"{k}={v}" for k, v in yt_cookies.items())
            user_agent = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
            raw_headers = "\n".join(
                [
                    f"Cookie: {cookie_header}",
                    f"User-Agent: {user_agent}",
                    "Accept: */*",
                    "Accept-Language: en-US,en;q=0.9",
                    "Content-Type: application/json",
                    "X-Goog-AuthUser: 0",
                    "x-origin: https://music.youtube.com",
                    # ytmusicapi flips to AuthType.BROWSER only when the
                    # authorization header contains "SAPISIDHASH". The actual
                    # hash is regenerated per-request from the cookie, so any
                    # placeholder works here.
                    "Authorization: SAPISIDHASH 0_placeholder",
                ]
            )

            if self.setup_from_headers(raw_headers):
                _status(f"Imported session from {browser}.")
                return True
            last_exc = self.last_error or "setup_from_headers failed"

        msg = (
            "Could not find a logged-in YouTube Music session in any supported "
            "browser (Chrome, Firefox, Brave, Edge). Sign in at "
            "music.youtube.com first."
        )
        if last_exc:
            msg = f"{msg} Last error: {last_exc}"
        logger.error(msg)
        self.last_error = msg
        _status(msg)
        return False

    def setup_from_headers(self, headers_raw: str) -> bool:
        """Configure auth from raw browser request headers."""
        try:
            from ytmusicapi import setup as _setup

            _setup(filepath=self.headers_file, headers_raw=headers_raw)
            logger.info("Browser-header auth setup complete")
            self.last_error = None
            return True
        except Exception as e:
            logger.error("Browser-header setup failed: %s", e)
            self.last_error = str(e)
            return False

    def get_ytmuxiris(self) -> object | None:
        """Return authenticated YTMusic instance or None."""
        active = self._active_auth_file()
        if active is None:
            return None
        try:
            from ytmusicapi import YTMusic

            # Only attach OAuthCredentials when we're using the OAuth token
            # file — they're useless (and slightly misleading) for browser
            # headers.
            if active == self.auth_file:
                client_id, client_secret = self._load_oauth_credentials()
                if client_id and client_secret:
                    from ytmusicapi.auth.oauth import OAuthCredentials

                    return YTMusic(
                        active,
                        oauth_credentials=OAuthCredentials(
                            client_id=client_id,
                            client_secret=client_secret,
                        ),
                    )
            return YTMusic(active)
        except Exception as e:
            logger.error("Failed to create YTMusic instance: %s", e)
            return None

    def logout(self) -> None:
        """Delete saved auth files."""
        try:
            Path(self.auth_file).unlink(missing_ok=True)
            Path(self.headers_file).unlink(missing_ok=True)
            logger.info("Logged out")
        except Exception as e:
            logger.error("Logout failed: %s", e)
