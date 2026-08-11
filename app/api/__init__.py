"""API routers package."""

from fastapi import APIRouter

from . import songs


router = APIRouter()
router.include_router(songs.router)
