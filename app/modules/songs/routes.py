"""HTTP surface for setlists and the songs in them.

Two routers, one module: `/setlists/{slug}` and `/setlists/{slug}/songs/...`
address the same aggregate, and the second is nested inside the first. They
are combined into one `router` at the bottom of the file.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from ...core.database import get_session
from ...core.http import etag_for, matches, parse_entity_tag
from ..auth import get_author
from . import merging, revisions, service, setlists, sync
from .schemas import (
    ReorderPayload,
    SetlistBase,
    SetlistChanges,
    SetlistState,
    SetlistUpdate,
    SongCreate,
    SongDetail,
    SongRevisionOut,
    SongSummary,
    SongUpdate,
)
from .versioning import require_match

setlist_router = APIRouter(prefix="/setlists", tags=["setlists"])
song_router = APIRouter(prefix="/setlists/{setlist_slug}/songs", tags=["songs"])


def _require_setlist(session, setlist_slug: str):
    setlist = setlists.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return setlist


def _tag(response: Response, detail: SongDetail) -> SongDetail:
    """Stamp the version on the response.

    `no-cache` does not disable caching — it tells the browser to keep the copy
    but revalidate it, which is exactly what makes the ETag useful.
    """

    response.headers["ETag"] = etag_for(detail.id, detail.rev)
    response.headers["Cache-Control"] = "no-cache"
    return detail


# --- The setlist itself, and the two endpoints clients poll ----------------


@setlist_router.get("/{setlist_slug}", response_model=SetlistBase)
def get_setlist(setlist_slug: str, session=Depends(get_session)):
    return setlists.to_base(_require_setlist(session, setlist_slug))


@setlist_router.patch("/{setlist_slug}", response_model=SetlistBase)
def update_setlist(setlist_slug: str, payload: SetlistUpdate, session=Depends(get_session)):
    setlist = _require_setlist(session, setlist_slug)
    return setlists.to_base(
        setlists.update_setlist(session, setlist, payload.name, payload.description)
    )


@setlist_router.get("/{setlist_slug}/changes", response_model=SetlistChanges)
def get_changes(
    setlist_slug: str,
    since: int = Query(default=0, ge=0),
    session=Depends(get_session),
):
    """What changed after `since` — the polling endpoint (roadmap phase 3).

    Deliberately cheap: on an unchanged setlist the response is a few dozen
    bytes, which is what makes polling on focus affordable without a socket.
    Answer `tooOld` and re-sync via /state when the cursor predates retained
    history.
    """

    setlist = _require_setlist(session, setlist_slug)
    return sync.get_changes(session, setlist, since)


@setlist_router.get("/{setlist_slug}/state", response_model=SetlistState)
def get_state(setlist_slug: str, session=Depends(get_session)):
    """Every live song as {id, rev} — cold reconciliation after a lost cursor."""

    setlist = _require_setlist(session, setlist_slug)
    return sync.get_state(session, setlist)


# --- Songs -----------------------------------------------------------------


@song_router.get("/", response_model=list[SongSummary])
def list_songs(
    setlist_slug: str,
    deleted: bool = False,
    session=Depends(get_session),
):
    """Live songs, or the trash when `?deleted=1`."""

    setlist = _require_setlist(session, setlist_slug)
    return service.list_songs(session, setlist, deleted=deleted)


@song_router.post("/", response_model=SongDetail, status_code=status.HTTP_201_CREATED)
def create_song(
    setlist_slug: str,
    payload: SongCreate,
    response: Response,
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    return _tag(response, service.create_song(session, setlist, payload, author=author))


@song_router.get("/{song_id}", response_model=SongDetail)
def get_song(
    setlist_slug: str,
    song_id: str,
    request: Request,
    response: Response,
    session=Depends(get_session),
):
    setlist = _require_setlist(session, setlist_slug)
    song = service.get_song(session, setlist, song_id, include_deleted=True)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Answer the conditional request before building the body: re-parsing the
    # markdown into lines is the expensive part of this endpoint.
    if matches(parse_entity_tag(request.headers.get("if-none-match")), song.id, song.rev):
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag_for(song.id, song.rev), "Cache-Control": "no-cache"},
        )

    detail = service.to_detail(song, setlist)
    if song.deleted_at is not None:
        response.headers["X-Deleted"] = "1"
    return _tag(response, detail)


@song_router.patch("/{song_id}", response_model=SongDetail)
def update_song(
    setlist_slug: str,
    song_id: str,
    payload: SongUpdate,
    response: Response,
    if_match: str | None = Header(default=None),
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    song = service.get_song(session, setlist, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    tag = parse_entity_tag(if_match)
    base_rev = tag[1] if tag else None

    if base_rev is not None and base_rev != song.rev:
        # Someone wrote in between. Before refusing, try to combine the two:
        # edits to different parts of a song are the ordinary case and should
        # not surface to anyone.
        outcome = merging.update_song_with_merge(
            session, setlist, song, payload, base_rev, author=author
        )
        if outcome.conflict:
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail={
                    "message": (
                        "Те же строки правил кто-то ещё"
                        if outcome.conflict == "lines"
                        else "Песня изменилась слишком давно, нужно обновить"
                    ),
                    "reason": outcome.conflict,
                    "songId": song_id,
                    "expectedRev": base_rev,
                    "currentRev": song.rev,
                    "current": service.to_detail(song, setlist).model_dump(
                        by_alias=True, mode="json"
                    ),
                },
            )
        response.headers["X-Merged"] = "true"
        if outcome.overwritten:
            response.headers["X-Overwritten-Fields"] = ",".join(outcome.overwritten)
        return _tag(response, outcome.detail)

    return _tag(response, service.update_song(session, setlist, song, payload, author=author))


@song_router.get("/{song_id}/revisions", response_model=list[SongRevisionOut])
def list_revisions(setlist_slug: str, song_id: str, session=Depends(get_session)):
    """Edit history — who changed the song and when. Falls out of the
    snapshots the merge already needs."""

    setlist = _require_setlist(session, setlist_slug)
    song = service.get_song(session, setlist, song_id, include_deleted=True)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return revisions.list_for_song(session, song_id)


@song_router.delete("/{song_id}", response_model=SongDetail)
def delete_song(
    setlist_slug: str,
    song_id: str,
    response: Response,
    if_match: str | None = Header(default=None),
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    """Soft delete. Returns the deleted song so the client can offer an undo
    without holding the pre-deletion state itself."""

    setlist = _require_setlist(session, setlist_slug)
    song = service.get_song(session, setlist, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    require_match(
        parse_entity_tag(if_match),
        song_id,
        song.rev,
        service.to_detail(song, setlist),
    )
    return _tag(response, service.delete_song(session, setlist, song, author=author))


@song_router.post("/{song_id}/restore", response_model=SongDetail)
def restore_song(
    setlist_slug: str,
    song_id: str,
    response: Response,
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    song = service.get_song(session, setlist, song_id, include_deleted=True)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    if song.deleted_at is None:
        # Already live — restoring again would burn a rev and wake every client
        # up for nothing.
        return _tag(response, service.to_detail(song, setlist))
    return _tag(response, service.restore_song(session, setlist, song, author=author))


@song_router.post("/reorder", response_model=list[SongSummary])
def reorder_songs(
    setlist_slug: str,
    payload: ReorderPayload,
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    return service.reorder_songs(session, setlist, payload.order, author=author)


# The setlist's own endpoints first: signing a client up to the change feed
# has to work before anything nested under it.
router = APIRouter()
router.include_router(setlist_router)
router.include_router(song_router)
