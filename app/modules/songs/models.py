"""Tables for the setlist and the songs in it.

One module, three tables, because they are one aggregate: a song's version
number is taken from a counter on its setlist, and the change feed the
frontend polls is a setlist-wide read over songs. Splitting them apart would
buy two package names and a dependency pointing both ways.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ...shared.ids import generate_public_id


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
    # Display name of whoever last wrote — see auth/authorship.py. Attribution
    # for the UI, not an authorisation check, and a plain string rather than a
    # foreign key so history survives an account being removed.
    updated_by: str | None = None
    # Soft deletion: the row stays until it is purged, so an accidental delete
    # can be undone long after the toast is gone.
    deleted_at: datetime | None = Field(default=None, index=True)


class SongRevision(SQLModel, table=True):
    """A snapshot of a song at one rev.

    Exists so a write based on an older version can still be merged: a
    three-way merge needs the common ancestor, and without history the server
    can only say "your version is stale, reload". Pruned to the last
    `REVISION_RETENTION` per song.

    The same table doubles as the song's edit history — who changed what and
    when — which is worth having on its own.
    """

    id: int | None = Field(default=None, primary_key=True)
    song_id: str = Field(foreign_key="song.id", index=True)
    rev: int = Field(index=True)
    markdown_body: str
    title: str
    key: str
    original_key: str | None = None
    bpm: int | None = None
    time_signature: str | None = None
    updated_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
