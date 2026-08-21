"""API routers package."""

from fastapi import APIRouter

from ..auth.routes import router as auth_router
from . import movable_shapes, pdf, setlists, songs


router = APIRouter()
# First so that signing in is reachable before anything that needs a session.
router.include_router(auth_router)
router.include_router(setlists.router)
router.include_router(songs.router)
router.include_router(pdf.router)
router.include_router(movable_shapes.router)
