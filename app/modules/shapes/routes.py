"""Movable chord-shape library routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ...core.database import get_session
from . import service
from .schemas import MovableShapeCreate, MovableShapeOut, MovableShapeUpdate

router = APIRouter(prefix="/movable-shapes", tags=["movable-shapes"])


@router.get("/", response_model=list[MovableShapeOut])
def list_movable_shapes(session=Depends(get_session)):
    return service.list_shapes(session)


@router.post("/", response_model=MovableShapeOut, status_code=status.HTTP_201_CREATED)
def create_movable_shape(payload: MovableShapeCreate, session=Depends(get_session)):
    return service.create_shape(session, payload)


@router.patch("/{shape_id}", response_model=MovableShapeOut)
def update_movable_shape(
    shape_id: str, payload: MovableShapeUpdate, session=Depends(get_session)
):
    shape = service.get_shape(session, shape_id)
    if not shape:
        raise HTTPException(status_code=404, detail="Shape not found")
    return service.update_shape(session, shape, payload)


@router.delete("/{shape_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movable_shape(shape_id: str, session=Depends(get_session)):
    shape = service.get_shape(session, shape_id)
    if not shape:
        raise HTTPException(status_code=404, detail="Shape not found")
    service.delete_shape(session, shape)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
