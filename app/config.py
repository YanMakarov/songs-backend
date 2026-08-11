"""Application configuration helpers."""

from __future__ import annotations

from functools import lru_cache
import os
from typing import List

from pydantic import BaseModel, field_validator


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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance built from environment variables."""

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
    )


settings = get_settings()
