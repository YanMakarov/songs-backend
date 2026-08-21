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

    # Monotonic counter shared by every song in the setlist. Each write takes
    # the next value and stores it on the song, so one number serves as the
    # song's version (for If-Match), as the cache key, and as a position in
    # the setlist-wide change feed.
    rev_counter: int = Field(default=0)
    # Highest rev whose row has been physically purged from the trash. A client
    # asking for changes since an earlier rev cannot be answered accurately and
    # is told to re-sync from scratch.
    purged_rev: int = Field(default=0)


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

    # See Setlist.rev_counter. Bumped on every write, including deletion and
    # restore, so the change feed never misses a transition.
    rev: int = Field(default=0, index=True)
    # Display name of whoever last wrote, taken from the X-Client-Name header.
    # Attribution for the UI, not an authorisation check — the header is
    # trivially forgeable until real sign-in exists.
    updated_by: str | None = None
    # Soft deletion: the row stays until it is purged, so an accidental delete
    # can be undone long after the toast is gone.
    deleted_at: datetime | None = Field(default=None, index=True)


class MovableShape(SQLModel, table=True):
    """A movable fretting pattern (e.g. "E-form barre minor") — the library's
    unit of storage. `root_string` (0=low E .. 5=high e) is whichever string
    carries the root note; `offsets` is a JSON-encoded array of 6 entries
    (int fret offset from the barre fret, or null for a muted string). The
    same shape is reused for every root by sliding the barre fret; which
    notes/quality it actually produces is derived, never stored.
    """

    id: str = Field(default_factory=generate_public_id, primary_key=True, index=True)
    name: str | None = None
    root_string: int
    offsets: str
    is_custom: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
