"""Song-related API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .. import crud
from ..database import get_session
from ..schemas import ReorderPayload, SongCreate, SongDetail, SongSummary, SongUpdate


router = APIRouter(prefix="/setlists/{setlist_slug}/songs", tags=["songs"])


@router.get("/", response_model=list[SongSummary])
def list_songs(setlist_slug: str, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud.list_songs(session, setlist)


@router.post("/", response_model=SongDetail, status_code=status.HTTP_201_CREATED)
def create_song(setlist_slug: str, payload: SongCreate, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud.create_song(session, setlist, payload)


@router.get("/{song_id}", response_model=SongDetail)
def get_song(setlist_slug: str, song_id: str, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    detail = crud.get_song_detail(session, setlist, song_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Song not found")
    return detail


@router.patch("/{song_id}", response_model=SongDetail)
def update_song(setlist_slug: str, song_id: str, payload: SongUpdate, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    song = crud.get_song(session, setlist, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return crud.update_song(session, setlist, song, payload)


@router.delete("/{song_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_song(setlist_slug: str, song_id: str, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    song = crud.get_song(session, setlist, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    crud.delete_song(session, song)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reorder", response_model=list[SongSummary])
def reorder_songs(setlist_slug: str, payload: ReorderPayload, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud.reorder_songs(session, setlist, payload.order)
