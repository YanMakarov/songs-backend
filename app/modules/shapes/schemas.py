"""API payloads for the movable-shape library."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ...core.schema import APIModel


class MovableShapeBase(APIModel):
    name: Optional[str] = None
    root_string: int
    offsets: List[Optional[int]]
    is_custom: bool = False


class MovableShapeCreate(MovableShapeBase):
    pass


class MovableShapeUpdate(APIModel):
    """Renaming a saved shape. Only the name is editable — the fretting
    pattern is the shape's identity, so a different pattern is a different
    shape, added and (if it was a mistake) deleted."""

    name: Optional[str] = None


class MovableShapeOut(MovableShapeBase):
    id: str
    created_at: datetime
