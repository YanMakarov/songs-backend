"""Reads and writes for the shape library.

`offsets` is stored as a JSON string rather than as six columns: the array is
always read and written whole, and a fretting pattern has no meaningful
per-string query. Encoding and decoding it is this module's job, which is why
these functions return plain dicts ready for `MovableShapeOut` rather than ORM
rows — a caller holding a row would have to know about the encoding too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from sqlmodel import Session, select

from .models import MovableShape
from .schemas import MovableShapeCreate, MovableShapeUpdate

#: Shipped with the code, not migrated in: the library has to be non-empty to
#: be useful, and a fresh database on a new machine should not start blank.
SEED_PATH = Path(__file__).parent / "data" / "seed.json"


def _to_out(shape: MovableShape) -> dict:
    return {
        "id": shape.id,
        "name": shape.name,
        "root_string": shape.root_string,
        "offsets": json.loads(shape.offsets),
        "is_custom": shape.is_custom,
        "created_at": shape.created_at,
    }


def list_shapes(session: Session) -> List[dict]:
    shapes = session.exec(select(MovableShape).order_by(MovableShape.created_at)).all()
    return [_to_out(s) for s in shapes]


def create_shape(session: Session, payload: MovableShapeCreate) -> dict:
    shape = MovableShape(
        name=payload.name,
        root_string=payload.root_string,
        offsets=json.dumps(payload.offsets),
        is_custom=payload.is_custom,
    )
    session.add(shape)
    session.commit()
    session.refresh(shape)
    return _to_out(shape)


def get_shape(session: Session, shape_id: str) -> MovableShape | None:
    return session.get(MovableShape, shape_id)


def update_shape(session: Session, shape: MovableShape, payload: MovableShapeUpdate) -> dict:
    name = (payload.name or "").strip()
    # An emptied field means "no name of my own" — the card falls back to
    # naming the shape by its root string, same as one saved without a name.
    shape.name = name or None
    session.add(shape)
    session.commit()
    session.refresh(shape)
    return _to_out(shape)


def delete_shape(session: Session, shape: MovableShape) -> None:
    session.delete(shape)
    session.commit()


def seed_if_empty(session: Session, seed_path: Path | None = None) -> None:
    """Fill an empty library from the shipped seed file.

    Only when empty: a user who has deleted a stock shape should not find it
    back after the next restart.
    """

    existing = session.exec(select(MovableShape.id).limit(1)).first()
    if existing:
        return
    with open(seed_path or SEED_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    for row in rows:
        session.add(
            MovableShape(
                name=row.get("name"),
                root_string=row["rootString"],
                offsets=json.dumps(row["offsets"]),
                is_custom=row.get("isCustom", False),
            )
        )
    session.commit()
