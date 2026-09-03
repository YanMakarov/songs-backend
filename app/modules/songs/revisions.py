"""Snapshots of a song at each rev.

Two jobs from one table: the ancestor a three-way merge needs, and the edit
history the interface shows. Every rev bump writes one, which is what makes
"every rev has a snapshot" an invariant a merge can rely on.
"""

from __future__ import annotations

from typing import List

from sqlmodel import Session, select

from .models import Song, SongRevision

#: How many snapshots to keep per song. Enough to merge against anything a
#: client could plausibly still be holding, small enough to ignore.
REVISION_RETENTION = 50


def record(session: Session, song: Song) -> None:
    """Snapshot the song at its current rev."""

    session.add(
        SongRevision(
            song_id=song.id,
            rev=song.rev,
            markdown_body=song.markdown_body,
            title=song.title,
            key=song.key,
            original_key=song.original_key,
            bpm=song.bpm,
            time_signature=song.time_signature,
            updated_by=song.updated_by,
        )
    )
    _prune(session, song.id)


def _prune(session: Session, song_id: str) -> None:
    stale = session.exec(
        select(SongRevision)
        .where(SongRevision.song_id == song_id)
        .order_by(SongRevision.rev.desc())
        .offset(REVISION_RETENTION)
    ).all()
    for revision in stale:
        session.delete(revision)


def get(session: Session, song_id: str, rev: int) -> SongRevision | None:
    """The snapshot a client's `If-Match` refers to, if we still have it."""

    return session.exec(
        select(SongRevision).where(SongRevision.song_id == song_id, SongRevision.rev == rev)
    ).first()


def list_for_song(session: Session, song_id: str) -> List[SongRevision]:
    return session.exec(
        select(SongRevision)
        .where(SongRevision.song_id == song_id)
        .order_by(SongRevision.rev.desc())
    ).all()


def drop_for_song(session: Session, song_id: str) -> None:
    """Discard a song's history — only for a row being physically purged."""

    for revision in session.exec(
        select(SongRevision).where(SongRevision.song_id == song_id)
    ).all():
        session.delete(revision)
