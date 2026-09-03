"""Tables for accounts and signed-in browsers.

They live in the auth module rather than in a shared models file because
nothing outside auth reads them: a song records its author as a display name
string, not as a foreign key, precisely so that history survives an account
being removed.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ...shared.ids import generate_public_id


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
    # Refreshed at most once a day (see sessions.py) so that reading does not
    # turn every GET into a write.
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(index=True)
    # Kept for the "where am I signed in" screen that comes with real account
    # management; nothing reads it yet.
    user_agent: str | None = None
