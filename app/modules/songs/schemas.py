"""API payloads for setlists, songs and the change feed."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from ...core.schema import APIModel


class SongChord(APIModel):
    id: str
    position: int = 0
    chord: str
    voicing: Optional[str] = None


class SongLine(APIModel):
    id: str
    # "comment" is a free-form note the performer leaves for themselves
    # ("попробовать другой аккорд здесь"); its text lives in `lyrics` like
    # any other textual line, so every consumer that falls back to `lyrics`
    # keeps showing something readable instead of an empty row.
    type: Literal["line", "section", "chords", "pagebreak", "comment"] = "line"
    lyrics: str = ""
    label: Optional[str] = None
    key: Optional[str] = None
    repeat_count: Optional[int] = None
    chords: List[SongChord] = Field(default_factory=list)


class SongBase(APIModel):
    id: str
    setlist_slug: str
    title: str
    key: str = "C"
    original_key: Optional[str] = None
    bpm: Optional[int] = None
    time_signature: str = "4/4"
    position: int = 0
    created_at: datetime
    updated_at: datetime
    # Monotonic per-setlist version. Send it back as `If-Match` when writing.
    rev: int = 0
    updated_by: Optional[str] = None
    # Set only for songs in the trash (`GET /songs/?deleted=1`).
    deleted_at: Optional[datetime] = None


class SongSummary(SongBase):
    pass


class SongDetail(SongBase):
    lines: List[SongLine]


class SongCreate(APIModel):
    title: Optional[str] = None
    key: Optional[str] = None
    original_key: Optional[str] = None
    bpm: Optional[int] = None
    time_signature: Optional[str] = None
    lines: Optional[List[SongLine]] = None


class SongUpdate(SongCreate):
    pass


class ReorderPayload(APIModel):
    order: List[str]


class SongChange(APIModel):
    """One entry of the setlist change feed.

    `song` is omitted for deletions so a client can drop the row without
    fetching anything; for live songs the summary is included, which is enough
    to refresh a list without a second round trip.
    """

    id: str
    rev: int
    deleted: bool = False
    updated_at: datetime
    updated_by: Optional[str] = None
    song: Optional[SongSummary] = None


class SetlistChanges(APIModel):
    #: The setlist's current rev — use it as `since` on the next poll.
    rev: int
    changes: List[SongChange] = Field(default_factory=list)
    #: The cursor reaches further back than retained history; re-sync via /state.
    too_old: bool = False


class SongState(APIModel):
    id: str
    rev: int


class SetlistState(APIModel):
    """Full {id, rev} listing for cold reconciliation after a lost cursor."""

    rev: int
    songs: List[SongState] = Field(default_factory=list)


class SongRevisionOut(APIModel):
    """One entry of a song's edit history."""

    rev: int
    title: str
    key: str
    bpm: Optional[int] = None
    updated_by: Optional[str] = None
    created_at: datetime


class ConflictDetail(APIModel):
    """Body of a 412 — carries the server's current state so the client does
    not need a second request to recover."""

    message: str
    current: SongDetail


class SetlistBase(APIModel):
    slug: str
    name: str
    description: Optional[str] = None


class SetlistUpdate(APIModel):
    name: Optional[str] = None
    description: Optional[str] = None
