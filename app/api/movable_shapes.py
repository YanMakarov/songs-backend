"""Movable chord-shape library routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .. import crud
from ..database import get_session
from ..schemas import MovableShapeCreate, MovableShapeOut

router = APIRouter(prefix="/movable-shapes", tags=["movable-shapes"])


@router.get("/", response_model=list[MovableShapeOut])
def list_movable_shapes(session=Depends(get_session)):
    return crud.list_movable_shapes(session)


@router.post("/", response_model=MovableShapeOut, status_code=status.HTTP_201_CREATED)
def create_movable_shape(payload: MovableShapeCreate, session=Depends(get_session)):
    return crud.create_movable_shape(session, payload)


@router.delete("/{shape_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movable_shape(shape_id: str, session=Depends(get_session)):
    shape = crud.get_movable_shape(session, shape_id)
    if not shape:
        raise HTTPException(status_code=404, detail="Shape not found")
    crud.delete_movable_shape(session, shape)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
