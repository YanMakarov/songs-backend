"""Setlist-related API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import crud
from ..database import get_session
from ..schemas import SetlistBase, SetlistUpdate


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
