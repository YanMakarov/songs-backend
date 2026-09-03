"""API payload for a parsed PDF."""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from ...core.schema import APIModel
from ..songs import SongLine


class PDFImportResult(APIModel):
    title: Optional[str] = None
    bpm: Optional[int] = None
    time_signature: Optional[str] = None
    primary_key: Optional[str] = None
    lines: List[SongLine] = Field(default_factory=list)
