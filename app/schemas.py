"""Pydantic schemas for API payloads."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class SongChord(APIModel):
    id: str
    position: int = 0
    chord: str


class SongLine(APIModel):
    id: str
    type: Literal["line", "section", "chords"] = "line"
    lyrics: str = ""
    label: Optional[str] = None
    key: Optional[str] = None
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
