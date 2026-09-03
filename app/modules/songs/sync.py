"""What the frontend polls to stay in step.

Two reads, both deliberately cheap. `get_changes` is the steady state — on an
unchanged setlist it answers in a few dozen bytes, which is what makes polling
on focus affordable without a socket. `get_state` is the fallback for a client
whose cursor no longer means anything.
"""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Setlist, Song
from .schemas import SetlistChanges, SetlistState, SongChange, SongState
from .service import to_summary


def get_changes(session: Session, setlist: Setlist, since: int) -> SetlistChanges:
    """Everything that changed after `since`, as ids plus summaries.

    Deletions carry no summary — the client already knows what to drop, and
    sending the body of a deleted song would be pure waste.
    """

    current = setlist.rev_counter or 0
    if since < (setlist.purged_rev or 0) or since > current:
        # Cursor is either older than retained history or from another database.
        return SetlistChanges(rev=current, changes=[], too_old=True)

    songs = session.exec(
        select(Song).where(Song.setlist_id == setlist.id, Song.rev > since).order_by(Song.rev)
    ).all()
    changes = [
        SongChange(
            id=song.id,
            rev=song.rev,
            deleted=song.deleted_at is not None,
            updated_at=song.updated_at,
            updated_by=song.updated_by,
            song=None if song.deleted_at is not None else to_summary(song, setlist),
        )
        for song in songs
    ]
    return SetlistChanges(rev=current, changes=changes, too_old=False)


def get_state(session: Session, setlist: Setlist) -> SetlistState:
    songs = session.exec(
        select(Song)
        .where(Song.setlist_id == setlist.id, Song.deleted_at.is_(None))
        .order_by(Song.position, Song.created_at)
    ).all()
    return SetlistState(
        rev=setlist.rev_counter or 0,
        songs=[SongState(id=song.id, rev=song.rev) for song in songs],
    )
