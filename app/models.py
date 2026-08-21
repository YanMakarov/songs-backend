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


class User(SQLModel, table=True):
    """Someone who can sign in.

    Deactivation rather than deletion is the normal way to remove access:
    `Song.updated_by` and every row in `SongRevision` hold a display name, and
    dropping the user would leave that history pointing at nobody. Revoking
    access is `is_active = False` plus deleting the user's sessions, which
    takes effect on the next request. Physical deletion stays available for
    the rare case where the row must genuinely go.
    """

    id: str = Field(default_factory=generate_public_id, primary_key=True, index=True)
    # Login handle. Lowercased on the way in so "Vasya" and "vasya" cannot
    # become two accounts.
    username: str = Field(index=True, unique=True)
    password_hash: str
    # What gets recorded as the author of a write, and shown in the conflict
    # banner. Separate from `username` so it can be changed freely.
    display_name: str
    # No admin HTTP surface exists yet — user management is the CLI in
    # app/cli.py. The column is here from the start so that adding one later
    # is a routing change rather than a migration.
    is_admin: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    deactivated_at: datetime | None = None


class AuthSession(SQLModel, table=True):
    """One signed-in browser.

    Named `AuthSession` and not `Session` so it never has to be aliased
    against SQLModel's own `Session` in modules that use both.

    Sessions live in the database rather than in a self-contained token
    because the first thing this app needs to do is take access away: an
    opaque token is revoked by deleting a row, while a JWT would need a
    revocation list — the same table, plus a layer.

    Only the SHA-256 of the token is stored. The cookie value itself never
    touches the database, so a leaked `songs.db` cannot be replayed as a
    login.
    """

    token_hash: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Refreshed at most once a day (see auth/sessions.py) so that reading does
    # not turn every GET into a write.
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(index=True)
    # Kept for the "where am I signed in" screen that comes with real account
    # management; nothing reads it yet.
    user_agent: str | None = None
