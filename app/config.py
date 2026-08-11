"""Application configuration helpers."""

from __future__ import annotations

from functools import lru_cache
import os
from typing import List

from pydantic import BaseModel, field_validator


class Settings(BaseModel):
    app_name: str = "Songs API"
    database_url: str = "sqlite:///./songs.db"
    cors_origins: List[str] = ["http://localhost:5173"]

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
    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.model_fields["database_url"].default),
        cors_origins=cors_raw or Settings.model_fields["cors_origins"].default,
    )


settings = get_settings()
