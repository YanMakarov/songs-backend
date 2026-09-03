"""Table for the movable-shape library."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ...shared.ids import generate_public_id


class MovableShape(SQLModel, table=True):
    """A movable fretting pattern (e.g. "E-form barre minor") — the library's
    unit of storage. `root_string` (0=low E .. 5=high e) is whichever string
    carries the root note; `offsets` is a JSON-encoded array of 6 entries
    (int fret offset from the barre fret, or null for a muted string). The
    same shape is reused for every root by sliding the barre fret; which
    notes/quality it actually produces is derived, never stored.
    """

    id: str = Field(default_factory=generate_public_id, primary_key=True, index=True)
    name: str | None = None
    root_string: int
    offsets: str
    is_custom: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
