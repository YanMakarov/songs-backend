"""What the songs module needs done when the process starts.

Kept here rather than in `main.py` so that the app layer wires modules without
knowing what any of them keeps in its tables — adding a second setlist or
changing the retention window is a change inside this module.
"""

from __future__ import annotations

from sqlmodel import Session

from .service import purge_deleted
from .setlists import ensure_setlist

#: The app is single-setlist for now; the slug is in the URL of every song, so
#: it stays a constant rather than becoming configuration.
DEFAULT_SLUG = "setlist1"
DEFAULT_NAME = "Setlist 1"

#: How long a soft-deleted song stays restorable.
TRASH_RETENTION_DAYS = 30


def on_startup(session: Session) -> None:
    setlist = ensure_setlist(session, slug=DEFAULT_SLUG, name=DEFAULT_NAME)
    purge_deleted(session, setlist, older_than_days=TRASH_RETENTION_DAYS)
