"""Database helpers for setlists and songs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Iterable, List

from sqlmodel import Session, select

from . import markdown_utils
from .models import MovableShape, Setlist, Song
from .schemas import (
    MovableShapeCreate,
    ReorderPayload,
    SetlistChanges,
    SetlistState,
    SongChange,
    SongState,
    SongCreate,
    SongDetail,
    SongLine,
    SongSummary,
    SongUpdate,
    SetlistBase,
)


def ensure_setlist(session: Session, slug: str, name: str) -> Setlist:
    setlist = session.exec(select(Setlist).where(Setlist.slug == slug)).first()
    if setlist:
        return setlist
    setlist = Setlist(slug=slug, name=name)
    session.add(setlist)
    session.commit()
    session.refresh(setlist)
    return setlist


def get_setlist(session: Session, slug: str) -> Setlist | None:
    return session.exec(select(Setlist).where(Setlist.slug == slug)).first()


def _to_setlist_base(setlist: Setlist) -> SetlistBase:
    return SetlistBase(
        slug=setlist.slug,
        name=setlist.name,
        description=setlist.description,
    )


def update_setlist(session: Session, setlist: Setlist, name: str | None, description: str | None) -> Setlist:
    if name is not None:
        setlist.name = name
    if description is not None:
        setlist.description = description
    session.add(setlist)
    session.commit()
    session.refresh(setlist)
    return setlist


def _next_rev(session: Session, setlist: Setlist) -> int:
    """Take the next value of the setlist's monotonic counter.

    Must run inside the same transaction as the write it is stamping, so a
    rev is never handed out for a change that then rolls back — the change
    feed would skip a number and clients would silently miss an update.
    """

    setlist.rev_counter = (setlist.rev_counter or 0) + 1
    session.add(setlist)
    return setlist.rev_counter


def _to_summary(song: Song, setlist: Setlist) -> SongSummary:
    return SongSummary(
        id=song.id,
        setlist_slug=setlist.slug,
        title=song.title,
        key=song.key,
        original_key=song.original_key,
        bpm=song.bpm,
        time_signature=song.time_signature,
        position=song.position,
        created_at=song.created_at,
        updated_at=song.updated_at,
        rev=song.rev,
        updated_by=song.updated_by,
        deleted_at=song.deleted_at,
    )


def _to_detail(song: Song, setlist: Setlist) -> SongDetail:
    lines = markdown_utils.markdown_to_lines(song.markdown_body)
    return SongDetail(
        id=song.id,
        setlist_slug=setlist.slug,
        title=song.title,
        key=song.key,
        original_key=song.original_key,
        bpm=song.bpm,
        time_signature=song.time_signature,
        position=song.position,
        created_at=song.created_at,
        updated_at=song.updated_at,
        rev=song.rev,
        updated_by=song.updated_by,
        deleted_at=song.deleted_at,
        lines=lines,
    )


def list_songs(session: Session, setlist: Setlist, *, deleted: bool = False) -> List[SongSummary]:
    """Live songs by default; `deleted=True` lists the trash, newest first."""

    query = select(Song).where(Song.setlist_id == setlist.id)
    if deleted:
        query = query.where(Song.deleted_at.is_not(None)).order_by(Song.deleted_at.desc())
    else:
        query = query.where(Song.deleted_at.is_(None)).order_by(Song.position, Song.created_at)
    return [_to_summary(song, setlist) for song in session.exec(query).all()]


def get_song(
    session: Session, setlist: Setlist, song_id: str, *, include_deleted: bool = False
) -> Song | None:
    song = session.exec(
        select(Song).where(Song.setlist_id == setlist.id, Song.id == song_id)
    ).first()
    if song and song.deleted_at is not None and not include_deleted:
        return None
    return song


def to_detail(song: Song, setlist: Setlist) -> SongDetail:
    """Public wrapper for building a detail payload from an already-loaded row,
    so routes that hold a `Song` do not have to look it up a second time."""

    return _to_detail(song, setlist)


def get_song_detail(session: Session, setlist: Setlist, song_id: str) -> SongDetail | None:
    song = get_song(session, setlist, song_id)
    if not song:
        return None
    return _to_detail(song, setlist)


def _next_position(session: Session, setlist: Setlist) -> int:
    last_song = session.exec(
        select(Song).where(Song.setlist_id == setlist.id).order_by(Song.position.desc())
    ).first()
    return (last_song.position + 1) if last_song else 0


def create_song(
    session: Session, setlist: Setlist, payload: SongCreate, *, author: str | None = None
) -> SongDetail:
    lines = payload.lines or markdown_utils.default_lines()
    if isinstance(lines, list):
        validated_lines = [SongLine.model_validate(line) for line in lines]
    else:
        validated_lines = markdown_utils.default_lines()
    markdown_body = markdown_utils.lines_to_markdown(validated_lines)
    now = datetime.utcnow()
    song = Song(
        setlist_id=setlist.id,
        title=payload.title or "Новая песня",
        key=payload.key or "C",
        original_key=payload.original_key,
        bpm=payload.bpm,
        time_signature=payload.time_signature or "4/4",
        markdown_body=markdown_body,
        position=_next_position(session, setlist),
        created_at=now,
        updated_at=now,
        rev=_next_rev(session, setlist),
        updated_by=author,
    )
    session.add(song)
    session.commit()
    session.refresh(song)
    return _to_detail(song, setlist)


def update_song(
    session: Session,
    setlist: Setlist,
    song: Song,
    payload: SongUpdate,
    *,
    author: str | None = None,
) -> SongDetail:
    if "title" in payload.model_fields_set:
        song.title = payload.title or ""
    if "key" in payload.model_fields_set and payload.key:
        song.key = payload.key
    if "original_key" in payload.model_fields_set:
        song.original_key = payload.original_key
    if "bpm" in payload.model_fields_set:
        song.bpm = payload.bpm
    if "time_signature" in payload.model_fields_set and payload.time_signature:
        song.time_signature = payload.time_signature
    if "lines" in payload.model_fields_set and payload.lines is not None:
        validated_lines = [SongLine.model_validate(line) for line in payload.lines]
        song.markdown_body = markdown_utils.lines_to_markdown(validated_lines)
    song.updated_at = datetime.utcnow()
    song.updated_by = author
    song.rev = _next_rev(session, setlist)
    session.add(song)
    session.commit()
    session.refresh(song)
    return _to_detail(song, setlist)


def delete_song(
    session: Session, setlist: Setlist, song: Song, *, author: str | None = None
) -> SongDetail:
    """Soft delete: the row stays in the trash until it is purged.

    Deletion is a normal write — it takes a rev like any other, so the change
    feed carries the transition and other clients can drop the song.
    """

    now = datetime.utcnow()
    song.deleted_at = now
    song.updated_at = now
    song.updated_by = author
    song.rev = _next_rev(session, setlist)
    session.add(song)
    session.commit()
    session.refresh(song)
    return _to_detail(song, setlist)


def restore_song(
    session: Session, setlist: Setlist, song: Song, *, author: str | None = None
) -> SongDetail:
    now = datetime.utcnow()
    song.deleted_at = None
    song.updated_at = now
    song.updated_by = author
    song.rev = _next_rev(session, setlist)
    session.add(song)
    session.commit()
    session.refresh(song)
    return _to_detail(song, setlist)


def purge_deleted(session: Session, setlist: Setlist, *, older_than_days: int = 30) -> int:
    """Physically remove trash older than the retention window.

    Purging loses history, so the highest purged rev is recorded: a client whose
    cursor predates it can no longer be told what changed and is sent to /state
    for a full re-sync instead of silently missing a deletion.
    """

    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    songs = session.exec(
        select(Song).where(
            Song.setlist_id == setlist.id,
            Song.deleted_at.is_not(None),
            Song.deleted_at < cutoff,
        )
    ).all()
    if not songs:
        return 0
    highest = max(song.rev for song in songs)
    for song in songs:
        session.delete(song)
    if highest > (setlist.purged_rev or 0):
        setlist.purged_rev = highest
        session.add(setlist)
    session.commit()
    return len(songs)


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
            song=None if song.deleted_at is not None else _to_summary(song, setlist),
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


def reorder_songs(
    session: Session, setlist: Setlist, order: Iterable[str], *, author: str | None = None
) -> List[SongSummary]:
    songs = session.exec(
        select(Song).where(Song.setlist_id == setlist.id, Song.deleted_at.is_(None))
    ).all()
    lookup = {song.id: song for song in songs}
    now = datetime.utcnow()
    next_position = 0
    moved: List[Song] = []
    for song_id in order:
        song = lookup.get(song_id)
        if not song:
            continue
        if song.position != next_position:
            moved.append(song)
        song.position = next_position
        next_position += 1
    # Append songs not listed to keep them at the end in existing order
    remaining = [song for song in songs if song.id not in order]
    for song in sorted(remaining, key=lambda s: s.position):
        if song.position != next_position:
            moved.append(song)
        song.position = next_position
        next_position += 1
    # Only songs that actually moved take a rev, otherwise a no-op reorder
    # would flood every other client's change feed.
    for song in moved:
        song.updated_at = now
        song.updated_by = author
        song.rev = _next_rev(session, setlist)
        session.add(song)
    session.commit()
    return list_songs(session, setlist)


def _shape_to_out(shape: MovableShape) -> dict:
    return {
        "id": shape.id,
        "name": shape.name,
        "root_string": shape.root_string,
        "offsets": json.loads(shape.offsets),
        "is_custom": shape.is_custom,
        "created_at": shape.created_at,
    }


def list_movable_shapes(session: Session) -> List[dict]:
    shapes = session.exec(select(MovableShape).order_by(MovableShape.created_at)).all()
    return [_shape_to_out(s) for s in shapes]


def create_movable_shape(session: Session, payload: MovableShapeCreate) -> dict:
    shape = MovableShape(
        name=payload.name,
        root_string=payload.root_string,
        offsets=json.dumps(payload.offsets),
        is_custom=payload.is_custom,
    )
    session.add(shape)
    session.commit()
    session.refresh(shape)
    return _shape_to_out(shape)


def get_movable_shape(session: Session, shape_id: str) -> MovableShape | None:
    return session.get(MovableShape, shape_id)


def delete_movable_shape(session: Session, shape: MovableShape) -> None:
    session.delete(shape)
    session.commit()


def seed_movable_shapes_if_empty(session: Session, seed_path) -> None:
    existing = session.exec(select(MovableShape.id).limit(1)).first()
    if existing:
        return
    with open(seed_path, encoding="utf-8") as f:
        rows = json.load(f)
    for row in rows:
        session.add(
            MovableShape(
                name=row.get("name"),
                root_string=row["rootString"],
                offsets=json.dumps(row["offsets"]),
                is_custom=row.get("isCustom", False),
            )
        )
    session.commit()
