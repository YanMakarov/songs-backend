"""Song-related API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from .. import crud
from ..database import get_session
from ..deps import get_author
from ..http_versioning import etag_for, matches, parse_entity_tag, require_match
from ..schemas import ReorderPayload, SongCreate, SongDetail, SongSummary, SongUpdate


router = APIRouter(prefix="/setlists/{setlist_slug}/songs", tags=["songs"])


def _require_setlist(session, setlist_slug: str):
    setlist = crud.get_setlist(session, setlist_slug)
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


@router.get("/", response_model=list[SongSummary])
def list_songs(
    setlist_slug: str,
    deleted: bool = False,
    session=Depends(get_session),
):
    """Live songs, or the trash when `?deleted=1`."""

    setlist = _require_setlist(session, setlist_slug)
    return crud.list_songs(session, setlist, deleted=deleted)


@router.post("/", response_model=SongDetail, status_code=status.HTTP_201_CREATED)
def create_song(
    setlist_slug: str,
    payload: SongCreate,
    response: Response,
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    return _tag(response, crud.create_song(session, setlist, payload, author=author))


@router.get("/{song_id}", response_model=SongDetail)
def get_song(
    setlist_slug: str,
    song_id: str,
    request: Request,
    response: Response,
    session=Depends(get_session),
):
    setlist = _require_setlist(session, setlist_slug)
    song = crud.get_song(session, setlist, song_id, include_deleted=True)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Answer the conditional request before building the body: re-parsing the
    # markdown into lines is the expensive part of this endpoint.
    if matches(parse_entity_tag(request.headers.get("if-none-match")), song.id, song.rev):
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag_for(song.id, song.rev), "Cache-Control": "no-cache"},
        )

    detail = crud.to_detail(song, setlist)
    if song.deleted_at is not None:
        response.headers["X-Deleted"] = "1"
    return _tag(response, detail)


@router.patch("/{song_id}", response_model=SongDetail)
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
    song = crud.get_song(session, setlist, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    require_match(
        parse_entity_tag(if_match),
        song_id,
        song.rev,
        crud.to_detail(song, setlist),
    )
    return _tag(response, crud.update_song(session, setlist, song, payload, author=author))


@router.delete("/{song_id}", response_model=SongDetail)
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
    song = crud.get_song(session, setlist, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    require_match(
        parse_entity_tag(if_match),
        song_id,
        song.rev,
        crud.to_detail(song, setlist),
    )
    return _tag(response, crud.delete_song(session, setlist, song, author=author))


@router.post("/{song_id}/restore", response_model=SongDetail)
def restore_song(
    setlist_slug: str,
    song_id: str,
    response: Response,
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    song = crud.get_song(session, setlist, song_id, include_deleted=True)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    if song.deleted_at is None:
        # Already live — restoring again would burn a rev and wake every client
        # up for nothing.
        return _tag(response, crud.to_detail(song, setlist))
    return _tag(response, crud.restore_song(session, setlist, song, author=author))


@router.post("/reorder", response_model=list[SongSummary])
def reorder_songs(
    setlist_slug: str,
    payload: ReorderPayload,
    session=Depends(get_session),
    author: str | None = Depends(get_author),
):
    setlist = _require_setlist(session, setlist_slug)
    return crud.reorder_songs(session, setlist, payload.order, author=author)
