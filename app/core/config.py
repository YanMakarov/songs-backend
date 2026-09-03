"""Application configuration helpers."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
import os
from typing import List

from pydantic import BaseModel, field_validator


class AuthMode(str, Enum):
    """How hard the API insists on a session.

    `REQUIRED` is the production setting and denies by default: every route
    not named in `auth.policy.PUBLIC_ROUTES` answers 401 without a session.
    A router added later is therefore closed until somebody opens it on
    purpose.

    `OPTIONAL` attaches the user when a session is present and never
    refuses. It exists for the step where parts of the setlist become
    readable without signing in: handlers can vary their answer by
    `current_user is None` instead of growing a third code path later.

    `DISABLED` turns authentication off. Intended for local development.
    Startup logs a banner and `/health` reports the mode, because a switch
    that can quietly open production is worse than no switch.
    """

    REQUIRED = "required"
    OPTIONAL = "optional"
    DISABLED = "disabled"


class Settings(BaseModel):
    app_name: str = "Songs API"
    database_url: str = "sqlite:///./songs.db"
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    cors_origin_regex: str | None = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    auth_mode: AuthMode = AuthMode.REQUIRED
    #: Name of the cookie carrying the session token.
    session_cookie_name: str = "songs_session"
    #: How long a session survives without being used. Long on purpose:
    #: the app is opened on stage, and a login prompt mid-rehearsal is a
    #: worse outcome than a long-lived cookie on a personal phone.
    session_ttl_days: int = 90
    #: `Secure` must be off over plain http or the browser drops the
    #: cookie, which makes local development impossible. On by default;
    #: turned off explicitly for localhost.
    session_cookie_secure: bool = True
    #: The frontend (songs.it-slon.ru) and the API (songs-api.it-slon.ru)
    #: share a registrable domain, so their requests count as same-site
    #: and `Lax` is enough. That also settles CSRF: a form on another site
    #: is cross-site and its request arrives without the cookie. Do not
    #: weaken this to `None` without adding a CSRF token.
    session_cookie_samesite: str = "lax"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance built from environment variables."""

    auth_raw = (os.getenv("SONGS_API_AUTH_MODE") or "").strip().lower()
    auth_mode = AuthMode(auth_raw) if auth_raw else Settings.model_fields["auth_mode"].default

    cors_raw = os.getenv("SONGS_API_CORS_ORIGINS") or os.getenv("CORS_ORIGINS") or ""
    cors_regex_env = os.getenv("SONGS_API_CORS_ORIGIN_REGEX") or os.getenv("CORS_ORIGIN_REGEX")
    if cors_regex_env is not None:
        cors_origin_regex = cors_regex_env.strip() or None
    else:
        cors_origin_regex = Settings.model_fields["cors_origin_regex"].default

    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.model_fields["database_url"].default),
        cors_origins=cors_raw or Settings.model_fields["cors_origins"].default,
        cors_origin_regex=cors_origin_regex,
        auth_mode=auth_mode,
        session_cookie_name=os.getenv(
            "SONGS_API_SESSION_COOKIE", Settings.model_fields["session_cookie_name"].default
        ),
        session_ttl_days=int(
            os.getenv("SONGS_API_SESSION_TTL_DAYS")
            or Settings.model_fields["session_ttl_days"].default
        ),
        session_cookie_secure=_flag(
            "SONGS_API_SESSION_COOKIE_SECURE",
            Settings.model_fields["session_cookie_secure"].default,
        ),
    )


settings = get_settings()
