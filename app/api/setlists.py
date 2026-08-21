"""Setlist-related API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import crud
from ..database import get_session
from ..schemas import SetlistBase, SetlistChanges, SetlistState, SetlistUpdate


router = APIRouter(prefix="/setlists", tags=["setlists"])


@router.get("/{setlist_slug}", response_model=SetlistBase)
def get_setlist(setlist_slug: str, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud._to_setlist_base(setlist)


@router.patch("/{setlist_slug}", response_model=SetlistBase)
def update_setlist(setlist_slug: str, payload: SetlistUpdate, session=Depends(get_session)):
    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud._to_setlist_base(
        crud.update_setlist(session, setlist, payload.name, payload.description)
    )


@router.get("/{setlist_slug}/changes", response_model=SetlistChanges)
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

    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud.get_changes(session, setlist, since)


@router.get("/{setlist_slug}/state", response_model=SetlistState)
def get_state(setlist_slug: str, session=Depends(get_session)):
    """Every live song as {id, rev} — cold reconciliation after a lost cursor."""

    setlist = crud.get_setlist(session, setlist_slug)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return crud.get_state(session, setlist)
