"""SQLModel ORM models."""

from __future__ import annotations

import secrets
import time
from datetime import datetime

from sqlmodel import Field, SQLModel


def generate_public_id() -> str:
    random_part = format(secrets.randbits(32), "x")
    timestamp_part = format(int(time.time() * 1000), "x")
    return (random_part + timestamp_part)[:20]


class Setlist(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Song(SQLModel, table=True):
    id: str = Field(default_factory=generate_public_id, primary_key=True, index=True)
    setlist_id: int = Field(foreign_key="setlist.id", index=True)
    title: str = Field(default="Новая песня")
    key: str = Field(default="C")
    original_key: str | None = None
    bpm: int | None = None
    time_signature: str | None = Field(default="4/4")
    markdown_body: str
    position: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
