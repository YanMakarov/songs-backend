"""API routers package."""

from fastapi import APIRouter

from . import movable_shapes, pdf, setlists, songs


router = APIRouter()
router.include_router(setlists.router)
router.include_router(songs.router)
router.include_router(pdf.router)
router.include_router(movable_shapes.router)
