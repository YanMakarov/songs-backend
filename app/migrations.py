"""Schema migrations for the SQLite database.

`SQLModel.metadata.create_all` creates missing tables but never alters existing
ones, so a new column on a model silently fails to appear in a database that
already has the table. Alembic is more machinery than a single-process SQLite
deployment needs; instead each migration is a numbered, idempotent function and
the last applied number is kept in `_migration`.

Rules for adding one: append to `MIGRATIONS` with the next number, never edit or
renumber an existing entry, and make the body safe to run twice.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _columns(conn: Connection, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).first()
    return row is not None


def _add_column(conn: Connection, table: str, column: str, ddl: str) -> None:
    if not _table_exists(conn, table):
        return
    if column in _columns(conn, table):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _migration_001_rev_and_soft_delete(conn: Connection) -> None:
    """Version, attribution and soft deletion (roadmap phase 1.1)."""

    _add_column(conn, "setlist", "rev_counter", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "setlist", "purged_rev", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "song", "rev", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "song", "updated_by", "VARCHAR")
    _add_column(conn, "song", "deleted_at", "DATETIME")

    if not _table_exists(conn, "song"):
        return

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_song_rev ON song (rev)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_song_deleted_at ON song (deleted_at)"))

    # Backfill: hand out revs in creation order per setlist so existing rows get
    # a consistent history, then point each setlist's counter past the highest.
    setlists = conn.execute(text("SELECT id FROM setlist")).fetchall()
    for (setlist_id,) in setlists:
        songs = conn.execute(
            text(
                "SELECT id FROM song WHERE setlist_id = :sid AND (rev IS NULL OR rev = 0)"
                " ORDER BY position, created_at, rowid"
            ),
            {"sid": setlist_id},
        ).fetchall()
        if not songs:
            continue
        start = conn.execute(
            text("SELECT COALESCE(MAX(rev), 0) FROM song WHERE setlist_id = :sid"),
            {"sid": setlist_id},
        ).scalar_one()
        rev = int(start)
        for (song_id,) in songs:
            rev += 1
            conn.execute(
                text("UPDATE song SET rev = :rev WHERE id = :id"),
                {"rev": rev, "id": song_id},
            )
        conn.execute(
            text("UPDATE setlist SET rev_counter = :rev WHERE id = :sid AND rev_counter < :rev"),
            {"rev": rev, "sid": setlist_id},
        )


MIGRATIONS: List[Tuple[int, str, Callable[[Connection], None]]] = [
    (1, "rev_and_soft_delete", _migration_001_rev_and_soft_delete),
]


def _current_version(conn: Connection) -> int:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS _migration ("
            " version INTEGER PRIMARY KEY,"
            " name VARCHAR NOT NULL,"
            " applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    return int(conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM _migration")).scalar_one())


def run_migrations(engine) -> List[str]:
    """Apply every migration newer than the recorded version. Returns names applied."""

    applied: List[str] = []
    with engine.begin() as conn:
        version = _current_version(conn)
        for number, name, migrate in MIGRATIONS:
            if number <= version:
                continue
            migrate(conn)
            conn.execute(
                text("INSERT INTO _migration (version, name) VALUES (:v, :n)"),
                {"v": number, "n": name},
            )
            applied.append(f"{number:03d}_{name}")
    return applied
