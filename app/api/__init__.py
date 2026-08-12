"""API routers package."""

from fastapi import APIRouter

from . import pdf, setlists, songs


router = APIRouter()
router.include_router(setlists.router)
router.include_router(songs.router)
router.include_router(pdf.router)
