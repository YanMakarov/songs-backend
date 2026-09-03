"""The setlist row itself, and the counter every song write draws from."""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Setlist
from .schemas import SetlistBase


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


def to_base(setlist: Setlist) -> SetlistBase:
    return SetlistBase(
        slug=setlist.slug,
        name=setlist.name,
        description=setlist.description,
    )


def update_setlist(
    session: Session, setlist: Setlist, name: str | None, description: str | None
) -> Setlist:
    if name is not None:
        setlist.name = name
    if description is not None:
        setlist.description = description
    session.add(setlist)
    session.commit()
    session.refresh(setlist)
    return setlist


def next_rev(session: Session, setlist: Setlist) -> int:
    """Take the next value of the setlist's monotonic counter.

    Must run inside the same transaction as the write it is stamping, so a
    rev is never handed out for a change that then rolls back — the change
    feed would skip a number and clients would silently miss an update.
    """

    setlist.rev_counter = (setlist.rev_counter or 0) + 1
    session.add(setlist)
    return setlist.rev_counter
