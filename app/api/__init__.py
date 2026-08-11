"""API routers package."""

from fastapi import APIRouter

from . import pdf, songs


router = APIRouter()
router.include_router(songs.router)
router.include_router(pdf.router)
